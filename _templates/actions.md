<%*
// Action launcher — reads the shared registry (single source of truth, also used
// by the "Vault Actions" panel in _HOME.md) and scaffolds the chosen template.
const REGISTRY_PATH = "_scripts/lib/actions-registry.json";
let categories;
try {
  categories = JSON.parse(await app.vault.adapter.read(REGISTRY_PATH)).categories;
} catch (e) {
  new Notice(`❌ Cannot read action registry: ${REGISTRY_PATH}`);
  return;
}

// Deep-link support — a dashboard button/menu may pre-set window._actionPreset:
//   { file: "<name>.md" } → run that template directly (skip both pickers)
//   { category: "<key>" } → jump straight to that category's template list
const preset = window._actionPreset;
window._actionPreset = null;                       // consume once

let chosenTmpl;
let chosenMode;
if (preset && preset.file) {
  chosenTmpl = preset.file;
  chosenMode = preset.mode;
  window._actionPreset = {
    mode: chosenMode,
    presetVal: preset.presetVal,
    targetFile: preset.targetFile
  };
} else {
  let chosenCat;
  if (preset && preset.category && categories.some((c) => c.key === preset.category)) {
    chosenCat = preset.category;                    // skip the category suggester
  } else {
    const catDisplay = categories.map((c) => c.display);
    const catValues = categories.map((c) => c.key);
    chosenCat = await tp.system.suggester(
      catDisplay,
      catValues,
      false,
      "What do you want to do?"
    );
  }
  if (!chosenCat) return;

  const cat = categories.find((c) => c.key === chosenCat);
  const tmplDisplay = cat.templates.map((t) => t.name);
  const tmplValues = cat.templates.map((t) => t.file);
  chosenTmpl = await tp.system.suggester(
    tmplDisplay,
    tmplValues,
    false,
    `${chosenCat} — choose a template`
  );
}
if (!chosenTmpl) return;

const tfile = app.vault.getAbstractFileByPath(`_scripts/templates/${chosenTmpl}`);
if (!tfile) {
  new Notice(`❌ Template not found: _scripts/templates/${chosenTmpl}`);
  return;
}
let content = await app.vault.read(tfile);
const sourceFile = app.workspace.getActiveFile();
if (sourceFile) {
  content = content.replace(/window\._actionsSourceFile/g, `app.vault.getAbstractFileByPath("${sourceFile.path.replace(/"/g, '\\"')}")`);
}
window._actionsSourceFile = sourceFile;

// Scratch buffer used to execute the chosen template. Self-moving templates
// (idea, protocol) turn this temp file INTO their real note via tp.file.move;
// self-creating templates write their own files and leave this temp behind.
// We always create it in a fixed scratch folder (never the active note's folder,
// which used to litter 00_STAGING/_daily/) and clean up through the INDEXED vault
// API (app.vault.delete) — NOT app.vault.adapter.remove. adapter.remove deletes the
// file on disk but leaves Obsidian's in-memory index pointing at it, so the next run
// (or Templater's getAvailablePath) tries to OPEN that ghost path and throws
// "ENOENT … __actions_temp__.md". Deleting through the vault keeps disk and index in
// sync; that also stops the "__actions_temp__ N.md" duplicates that were the real
// reason .trash kept filling up. If a self-moving template (idea/protocol) already
// turned the temp INTO its real note, getAbstractFileByPath returns null below, so
// the real note is never touched.
const TMP_DIR = "00_STAGING/_tmp";
const TMP_NAME = "__actions_temp__";
const tempPath = `${TMP_DIR}/${TMP_NAME}.md`;

if (!app.vault.getAbstractFileByPath(TMP_DIR)) {
  try { await app.vault.createFolder(TMP_DIR); } catch (e) {}
}

// Sweep leftovers from previous runs so Templater doesn't spawn "__actions_temp__ N.md".
for (const f of app.vault.getMarkdownFiles()) {
  if (f.basename.startsWith(TMP_NAME)) {
    try { await app.vault.delete(f, true); } catch (e) {}
  }
}

const backgroundTemplates = new Set([
  "new-journal-round.md",
  "new-peer-round.md",
  "new-latex-abstract.md",
  "peer-review.md",
  "people-db.md",
  "view-person.md",
  "file-recover.md",
  "pdf-to-md.md",
  "export-to-latex.md",
  "transcribe-audio.md"
]);
const openNew = !backgroundTemplates.has(chosenTmpl);
await tp.file.create_new(content, TMP_NAME, openNew, TMP_DIR);

try {
  const leftover = app.vault.getAbstractFileByPath(tempPath);
  if (leftover) await app.vault.delete(leftover, true);
} catch (e) {
  console.error("Failed to remove temp file:", e);
}
%>
