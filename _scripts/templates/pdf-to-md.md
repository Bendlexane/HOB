<%*
// Template: pdf-to-md
// Convert a PDF to Markdown. Output log → 00_STAGING/pdf-to-md-log.md

const vaultPath = app.vault.adapter.basePath;
const script    = `${vaultPath}/_scripts/automation/pdf_to_md.py`;
const fs        = require('fs');
const path      = require('path');
const { exec }  = require('child_process');

function getSubdirs(baseDir, maxDepth, depth = 0) {
    const results = [];
    if (depth >= maxDepth) return results;
    let entries;
    try { entries = fs.readdirSync(baseDir, { withFileTypes: true }); }
    catch (e) { return results; }
    for (const e of entries) {
        if (!e.isDirectory()) continue;
        if (e.name.startsWith('.') || e.name.startsWith('_')) continue;
        const full = path.join(baseDir, e.name);
        results.push(full);
        results.push(...getSubdirs(full, maxDepth, depth + 1));
    }
    return results;
}

// ── 1. PDF path — native macOS file picker ────────────────────────────────────
const pickedPath = await new Promise((resolve) => {
    exec(
        `osascript -e 'POSIX path of (choose file with prompt "Select a PDF to convert" of type {"pdf"})'`,
        (err, stdout) => resolve(err ? null : stdout.trim())
    );
});
if (!pickedPath) { new Notice("Cancelled."); return; }
const cleanPdf = pickedPath;
const defaultName = cleanPdf.split("/").pop().replace(/\.pdf$/i, "");

// ── 2. Output filename ────────────────────────────────────────────────────────
const outName = await tp.system.prompt(
    "Output filename (without .md)",
    defaultName,
    true
);
if (!outName) { new Notice("Cancelled."); return; }

// ── 3. Backend ────────────────────────────────────────────────────────────────
const backend = await tp.system.suggester(
    [
        "fast    ⚡⚡ pymupdf4llm — seconds, text-based PDFs (recommended)",
        "marker  ⚡   marker_single — minutes, complex layouts/figures",
        "glm-ocr 🐢   Ollama vision — very slow, scanned/image-only PDFs",
    ],
    ["fast", "marker", "glm-ocr"],
    false,
    "Conversion backend"
);
if (!backend) { new Notice("Cancelled."); return; }

// ── 4. DPI (glm-ocr only) ─────────────────────────────────────────────────────
let dpiVal = "150";
if (backend === "glm-ocr") {
    const d = await tp.system.suggester(
        ["150 DPI — fast (default)", "200 DPI — higher quality"],
        ["150", "200"],
        false, "DPI"
    );
    if (!d) { new Notice("Cancelled."); return; }
    dpiVal = d;
}

// ── 5. Mode ───────────────────────────────────────────────────────────────────
const mode = await tp.system.suggester(
    ["Run — full conversion", "Dry run — page 1 preview only"],
    ["run", "dry"],
    false, "Mode"
);
if (!mode) { new Notice("Cancelled."); return; }
const dryFlag = mode === "dry" ? "--dry-run" : "";

// ── 6. Destination ────────────────────────────────────────────────────────────
const knowledgeRoot = `${vaultPath}/03_KNOWLEDGE`;
const allDirs = [knowledgeRoot, ...getSubdirs(knowledgeRoot, 4), `${vaultPath}/00_STAGING`];
const labels  = allDirs.map(d => d.replace(vaultPath + '/', ''));
const dest = await tp.system.suggester(labels, allDirs, false, "Save Markdown to…");
if (!dest) { new Notice("Cancelled."); return; }

// ── 6b. Literature destination → require a citekey (literature.schema.yaml) ────
// Notes in 03_KNOWLEDGE/literature/ are identified by citekey, which is also the
// filename stem. Any other destination keeps the free-form output name.
let citekeyFlag = "";
let finalName = outName.trim();
if (dest.endsWith("/literature")) {
    const ck = await tp.system.prompt(
        "Citekey (author_year_keyword — lowercase, becomes the filename)",
        finalName.toLowerCase().replace(/[^a-z0-9_-]+/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, ""),
        true
    );
    if (!ck) { new Notice("Cancelled."); return; }
    finalName = ck.trim();
    citekeyFlag = `--citekey "${finalName}"`;
}

const outFile = `${dest}/${finalName}.md`;

// ── 7. Run, redirect output to log ───────────────────────────────────────────
const logPath = `${vaultPath}/00_STAGING/pdf-to-md-log.md`;
const cmd = `python3.10 "${script}" "${cleanPdf}" "${outFile}" --backend ${backend} --dpi ${dpiVal} ${citekeyFlag} ${dryFlag} > "${logPath}" 2>&1`;

new Notice(`⏳ Running ${backend}… log → 00_STAGING/pdf-to-md-log.md`, 5000);

try {
    await new Promise((resolve, reject) => {
        exec(cmd, { shell: true, maxBuffer: 100 * 1024 * 1024 }, (err) => {
            err ? reject(err) : resolve();
        });
    });
} catch (err) {
    // errors visible in log
}

// ── 8. Open log ───────────────────────────────────────────────────────────────
await new Promise(r => setTimeout(r, 800));
try {
    await app.workspace.openLinkText("00_STAGING/pdf-to-md-log.md", "", true);
    new Notice("✅ Done — see pdf-to-md-log for details.");
} catch (e) {
    new Notice("✅ Done — open 00_STAGING/pdf-to-md-log.md manually.");
}
%>
