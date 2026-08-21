/**
 * Zotero Actions & Tags — Export Annotations to Obsidian (Full-Text Synthesis in Background)
 *
 * INSTALLATION in Zotero → Tools → Actions & Tags → "+":
 *   Event:      openItem   (fires on PDF open; OR leave empty for any event)
 *   Operation:  customScript
 *   Menu Label: Export to Obsidian    ← makes it appear in the PDF reader dropdown menu
 *   Shortcut:   (optional, e.g. Ctrl+Shift+E)
 *   Data:       paste the contents of this file
 *
 */

// ── Configuration ────────────────────────────────────────────────────────────
// ⚠️ EDIT THESE before pasting into Zotero — this script runs inside Zotero's
// own JS sandbox and cannot read the vault's .env. See _scripts/automation/README.md.
const VAULT_ROOT   = "/CHANGE/ME/path/to/your/vault";
const PYTHON_PATH  = "/CHANGE/ME/path/to/python3";

const DESTINATIONS = [
  { label: "_currently-reading  (default)", path: `${VAULT_ROOT}/00_STAGING/_currently-reading` },
  { label: "00_STAGING", path: `${VAULT_ROOT}/00_STAGING` },
  { label: "03_KNOWLEDGE/literature", path: `${VAULT_ROOT}/03_KNOWLEDGE/literature` },
];

// Color -> label (matching the python script)
const COLOR_MAP = {
  "#ec2814": "red",    "#ff6666": "red",    "#fb5c89": "pink",  "#f5a7af": "pink",
  "#ffd400": "yellow", "#facd5a": "yellow", "#ffed99": "yellow", "#ffd100": "yellow",
  "#ffeb6b": "yellow", "#fefbce": "yellow",
  "#7cc868": "green",  "#5fb236": "green",  "#c3f0a9": "green",
  "#2ea8e5": "blue",   "#69b0f1": "blue",   "#aff5ff": "blue",
  "#a28ae5": "purple", "#9999ff": "purple", "#c885da": "purple",
  "#f19837": "orange",
  "#aaaaaa": "grey",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function colorLabel(hex) {
  return hex ? (COLOR_MAP[hex.toLowerCase()] || hex.toLowerCase()) : "other";
}

function stripHtml(html) {
  return (html || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<\/h[1-6]>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&nbsp;/g, " ").replace(/&quot;/g, '"')
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

// List subfolders of PROJECTS_DIR (skipping hidden files and .md files)
async function getProjectFolders() {
  try {
    const paths = await IOUtils.getChildren(`${VAULT_ROOT}/01_PROJECTS`);
    const folders = [];
    for (const p of paths) {
      const name = p.split("/").pop();
      if (name.startsWith(".") || name.startsWith("_") || name.endsWith(".md")) continue;
      try {
        const info = await IOUtils.stat(p);
        if (info.type === "directory") folders.push(name);
      } catch (_) {}
    }
    return folders.sort();
  } catch (_) {
    return [];
  }
}

// ── Main ──────────────────────────────────────────────────────────────────────

(async () => {

  // ── 1. Resolve selected item ──────────────────────────────────────────────
  let target = item ?? (typeof items !== "undefined" ? items?.[0] : null);
  if (!target) {
    Services.prompt.alert(null, "Export", "No item found. Please open a document in the PDF reader first.");
    return;
  }
  if (target.isAttachment()) {
    target = target.parentItem ?? Zotero.Items.get(target.parentItemID);
  }
  if (!target || target.isNote() || target.isAnnotation()) {
    Services.prompt.alert(null, "Export", "Unable to resolve a library item from the current attachment.");
    return;
  }

  // ── 2. Metadata ────────────────────────────────────────────────────────────
  const title    = target.getField("title")           || "(no title)";
  const rawDate  = target.getField("date")            || "";
  const year     = rawDate.match(/\b(19|20)\d{2}\b/)?.[0] || "";
  const doi      = target.getField("DOI")             || "";
  const abstract = target.getField("abstractNote")    || "";
  const journal  = target.getField("publicationTitle") || target.getField("bookTitle") || "";
  const volume   = target.getField("volume")          || "";
  const issue    = target.getField("issue")           || "";
  const pages    = target.getField("pages")           || "";
  const zoteroKey = target.key;

  const creators = target.getCreators();
  const authors  = creators.map(c => c.firstName ? `${c.lastName}, ${c.firstName}` : c.lastName);
  const tags     = target.getTags().map(t => t.tag).filter(Boolean);

  // ── 3. Citekey BetterBibTeX ────────────────────────────────────────────────
  let citekey;
  try {
    citekey = Zotero.BetterBibTeX.KeyManager.get(target.id).citationKey;
  } catch (_) {
    const last = (authors[0] || "unknown").split(",")[0].toLowerCase().replace(/[^a-z]/g, "");
    const kw   = title.split(/\s+/).find(w => w.length > 4)?.toLowerCase().replace(/[^a-z]/g, "") || "paper";
    citekey = `${last}_${year || "nd"}_${kw}`;
  }

  // ── 4. Annotations ─────────────────────────────────────────────────────────
  const annotations = [];
  let pdfPath = "";
  for (const attID of target.getAttachments()) {
    const att = Zotero.Items.get(attID);
    if (!att?.isPDFAttachment()) continue;
    
    // Resolve absolute PDF path
    const resolvedPath = att.getFilePath();
    if (resolvedPath && !pdfPath) {
      pdfPath = resolvedPath;
    }
    
    for (const ann of (att.getAnnotations() || [])) {
      if (ann.annotationType === "image") continue;  // skip area/image selections
      annotations.push({
        type:      ann.annotationType,
        text:      (ann.annotationText    || "").trim(),
        comment:   (ann.annotationComment || "").trim(),
        color:     ann.annotationColor    || "",
        page:      ann.annotationPageLabel || "",
        sortIndex: ann.annotationSortIndex || "",
      });
    }
  }
  annotations.sort((a, b) => a.sortIndex.localeCompare(b.sortIndex));

  // ── 5. Mode Selection ─────────────────────────────────────────────────────
  const modes = [
    "1. Highlights only (Standard Mode)",
    "2. Full-text synthesis (For Papers)",
    "3. Chapter-by-chapter synthesis (For Books)"
  ];
  const modeIdx = { value: 0 };
  const okMode = Services.prompt.select(
    null, "Export Mode",
    "Select export mode:",
    modes, modeIdx
  );
  if (!okMode) return;
  let selectedMode = String(modeIdx.value + 1);

  if (!pdfPath && (selectedMode === "2" || selectedMode === "3")) {
    Services.prompt.alert(
      null, "⚠️ PDF not found",
      "No PDF file path was found for this item.\nReverting to Mode 1 (Highlights only)."
    );
    selectedMode = "1";
  }

  // ── 6. Destination Selection ──────────────────────────────────────────────
  const destLabels = DESTINATIONS.map(d => d.label);
  const destIdx    = { value: 0 };
  const okDest = Services.prompt.select(
    null, "Export to Obsidian",
    `"${title.slice(0, 70)}${title.length > 70 ? "…" : ""}"`,
    destLabels, destIdx
  );
  if (!okDest) return;
  const destPath  = DESTINATIONS[destIdx.value].path;
  const destLabel = DESTINATIONS[destIdx.value].label.trim();

  // ── 7. Project Selection ──────────────────────────────────────────────────
  const projects      = await getProjectFolders();
  const projectLabels = ["— none", ...projects];
  const projIdx       = { value: 0 };
  Services.prompt.select(
    null, "Project Code",
    "Assign this note to a project:",
    projectLabels, projIdx
  );
  const projectCode = projIdx.value > 0 ? projects[projIdx.value - 1] : "";

  // ── 8. Overwrite Check ────────────────────────────────────────────────────
  const filePath = `${destPath}/${citekey}.md`;
  try {
    if (await IOUtils.exists(filePath)) {
      const overwrite = Services.prompt.confirm(
        null, "File already exists",
        `${citekey}.md already exists in ${destLabel}.\nOverwrite?`
      );
      if (!overwrite) return;
    }
  } catch (_) {}

  // ── 9. Write Temporary JSON File ──────────────────────────────────────────
  const tempJsonPath = `${VAULT_ROOT}/00_STAGING/_tmp/zotero_export_temp.json`;
  
  const formattedAnnotations = annotations.map(ann => ({
    type:        ann.type,
    text:        ann.text,
    comment:     ann.comment,
    color:       ann.color,
    color_label: colorLabel(ann.color),
    page:        ann.page,
    sortIndex:   ann.sortIndex
  }));

  const exportData = {
    citekey: citekey,
    title: title,
    authors: authors,
    year: year,
    journal: journal,
    doi: doi,
    abstract: abstract,
    volume: volume,
    issue: issue,
    pages: pages,
    mode: selectedMode,
    annotations: formattedAnnotations,
    tags: tags,
    // Routed through the JSON (UTF-8 safe) instead of argv: nsIProcess.run()
    // drops non-ASCII bytes (em-dashes, curly apostrophes, accents) from
    // command-line arguments on macOS, which corrupts these paths.
    pdf: pdfPath || "",
    dest: destPath,
    project: projectCode
  };

  try {
    await Zotero.File.putContentsAsync(tempJsonPath, JSON.stringify(exportData, null, 2));
  } catch (e) {
    Services.prompt.alert(null, "Export failed", `Failed to write temporary JSON file: ${e.message}`);
    return;
  }

  // ── 10. Start Python Background Process ────────────────────────────────────
  try {
    const file = Components.classes["@mozilla.org/file/local;1"]
                           .createInstance(Components.interfaces.nsIFile);
    file.initWithPath(PYTHON_PATH);

    const process = Components.classes["@mozilla.org/process/util;1"]
                            .createInstance(Components.interfaces.nsIProcess);
    process.init(file);

    const args = [
      `${VAULT_ROOT}/_scripts/automation/zotero_export_background.py`,
      "--json", tempJsonPath,
      "--pdf", pdfPath || "",
      "--dest", destPath,
      "--project", projectCode
    ];

    process.run(false, args, args.length); // asynchronous execution

    const pw = new Zotero.ProgressWindow({ closeOnClick: true });
    pw.changeHeadline(`⏳ Background synthesis started`);
    pw.addDescription(`${annotations.length} annotations · Mode ${selectedMode}`);
    pw.show();
    pw.startCloseTimer(4000);
  } catch (e) {
    Services.prompt.alert(null, "Background Process Error", `❌ Unable to start background worker: ${e.message}`);
    Zotero.logError(`[Export] Subprocess failed: ${e}`);
  }

})();
