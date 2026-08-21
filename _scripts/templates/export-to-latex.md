<%*
// Template: export-to-latex
// Export the current note to .tex or .pdf via Pandoc.

const { exec } = require('child_process');
const path      = require('path');
const fs        = require('fs');
const os        = require('os');

// ── 1. Current note ───────────────────────────────────────────────────────────
// When launched via actions.md, focus has shifted to __actions_temp__ —
// use the source file saved by the orchestrator if available.
const activeFile = window._actionsSourceFile || app.workspace.getActiveFile();
delete window._actionsSourceFile;
if (!activeFile) { new Notice("❌ No active note."); return; }

const vaultPath = app.vault.adapter.basePath;
const noteStem  = activeFile.basename;
const noteDir   = path.join(vaultPath, path.dirname(activeFile.path));

// ── 2. Choose output format ───────────────────────────────────────────────────
const format = await tp.system.suggester(
    [
        "📄 LaTeX (.tex) — source file, edit before compiling",
        "📕 PDF (.pdf)   — ready to read, via LaTeX engine",
    ],
    ["tex", "pdf"],
    false,
    "Export format"
);
if (!format) { new Notice("Cancelled."); return; }

// ── 3. Pick output folder (file manager opens on note's directory) ────────────
const pickedDir = await new Promise(resolve => {
    exec(
        `osascript -e 'POSIX path of (choose folder with prompt "Export to ${format.toUpperCase()} in…" default location POSIX file "${noteDir}")'`,
        (err, stdout) => resolve(err ? null : stdout.trim().replace(/\/$/, ""))
    );
});
if (!pickedDir) { new Notice("Cancelled."); return; }

// ── 4. Resolve Obsidian embeds → standard Markdown images ─────────────────────
// Pandoc doesn't understand ![[image.png]] wikilink embeds, so rewrite them to
// ![](</abs/path>) using Obsidian's own link resolver (works from any folder,
// including _attachments). Angle brackets let paths with spaces work. No width
// is set unless the embed specifies one (|300), so Pandoc caps images to the
// page (\maxwidth/\maxheight) and tall screenshots never overflow.
const IMG_EXT = new Set(["png","jpg","jpeg","gif","webp","bmp","tif","tiff","pdf"]);
const EMBED   = /!\[\[\s*([^\]|#]+?)\s*(?:#[^\]|]*)?(?:\|\s*([^\]]*?)\s*)?\]\]/g;

let content  = await app.vault.read(activeFile);
let missing  = [];
content = content.replace(EMBED, (whole, link, opt) => {
    const dest = app.metadataCache.getFirstLinkpathDest(link, activeFile.path);
    if (!dest) { missing.push(link); return whole; }         // unresolved: leave as-is
    if (!IMG_EXT.has(dest.extension.toLowerCase())) return whole; // e.g. note transclusion
    const abs = path.join(vaultPath, dest.path);
    // Obsidian size syntax: |300 (width px) or |300x200 (width x height px)
    let attr = "";
    if (opt) {
        const m = /^(\d+)(?:x(\d+))?$/.exec(opt);
        if (m) attr = m[2] ? `{width=${m[1]}px height=${m[2]}px}` : `{width=${m[1]}px}`;
    }
    return `![](<${abs}>)${attr}`;
});

// Write the rewritten Markdown to a temp file and feed that to Pandoc.
const tmpInput = path.join(os.tmpdir(), `obsidian-export-${Date.now()}.md`);
fs.writeFileSync(tmpInput, content, "utf8");

// ── 5. Build output path & command ───────────────────────────────────────────
const outputPath = `${pickedDir}/${noteStem}.${format}`;
const pandoc     = "/opt/homebrew/bin/pandoc";
// PDF: compile with LuaLaTeX and a styled header. The header uses the
// Unicode-rich Libertinus font, so scientific symbols typed directly in the
// note (ρ, σ, ≈, ≤, ×, ±, →, µ, R², …) render natively — no math markup or
// per-character mapping needed.
const styleHeader = path.join(vaultPath, "_scripts/pandoc/peer-review-style.tex");
const engineFlag  = format === "pdf" ? " --pdf-engine=/Library/TeX/texbin/lualatex" : "";
const headerFlag  = format === "pdf" ? ` -H "${styleHeader}"` : "";
// --resource-path lets any remaining relative links resolve against the vault.
const cmd = `"${pandoc}" "${tmpInput}" -o "${outputPath}" --resource-path "${vaultPath}"${engineFlag}${headerFlag}`;

new Notice(`⏳ Exporting to ${format.toUpperCase()}…`, 5000);

try {
    await new Promise((resolve, reject) => {
        exec(cmd, { shell: true }, (err, _stdout, stderr) => {
            err ? reject(stderr || err.message) : resolve();
        });
    });
    const warn = missing.length ? ` (⚠️ unresolved: ${missing.join(", ")})` : "";
    new Notice(`✅ Exported → ${pickedDir}/${noteStem}.${format}${warn}`);
} catch (err) {
    new Notice(`❌ Pandoc error: ${err}`);
} finally {
    try { fs.unlinkSync(tmpInput); } catch (_) {}
}
%>
