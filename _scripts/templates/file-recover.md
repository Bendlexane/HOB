<%*
// Template: file-recover
// Recover deleted files, restore past versions, preview history, browse git backups.

const { exec } = require('child_process');
const vaultPath = app.vault.adapter.basePath;

// ── Run a git command from vault root ─────────────────────────────────────────
function git(cmd) {
    return new Promise((resolve, reject) => {
        exec(
            `git -C "${vaultPath}" ${cmd}`,
            { shell: true, maxBuffer: 10 * 1024 * 1024 },
            (err, stdout, stderr) => err ? reject(stderr || err.message) : resolve(stdout)
        );
    });
}

// ── Parse `git log --oneline` → [{hash, message}] ────────────────────────────
function parseLog(raw) {
    return raw.trim().split('\n').filter(Boolean).map(line => ({
        hash: line.slice(0, 7),
        message: line.slice(8).trim()
    }));
}

// ── Show preview snippet in a persistent Notice while asking confirmation ─────
async function confirmRestore(filename, content) {
    const snippet = content.split('\n').filter(l => l.trim()).slice(0, 7).join('\n');
    const preview = snippet.length > 320 ? snippet.slice(0, 320) + '\n…' : snippet;
    const n = new Notice(`📋 Preview of "${filename}":\n\n${preview}`, 0);
    const choice = await tp.system.suggester(
        ["✅  Yes, restore this version", "❌  No, cancel"],
        ["yes", "no"],
        false,
        `Restore "${filename}"?`
    );
    n.hide();
    return choice === "yes";
}

// ── Ensure parent directories exist before writing ───────────────────────────
async function ensureParentDir(relPath) {
    const parts = relPath.split('/');
    parts.pop();
    if (!parts.length) return;
    const dir = parts.join('/');
    try { await app.vault.createFolder(dir); } catch (_) { /* already exists */ }
}

// ── 1. Mode selection ─────────────────────────────────────────────────────────
let mode;
let presetVal;
let targetFile;
if (window._actionPreset) {
    mode = window._actionPreset.mode;
    presetVal = window._actionPreset.presetVal;
    targetFile = window._actionPreset.targetFile;
    window._actionPreset = null; // consume
} else {
    mode = await tp.system.suggester(
        [
            "🗑️  Recover deleted file    — A file disappeared from the vault. Find it in git backups and bring it back.",
            "🔄  Restore past version    — The file exists but was accidentally modified. Roll it back to an earlier backup.",
            "👁️  Preview a past version  — See what a file looked like at a specific backup, without changing anything.",
            "📦  Recover renamed file    — A file was moved or renamed. Restore it to its original location.",
            "🔍  Browse a backup commit  — See all files touched in a specific backup (read-only).",
        ],
        ["A", "B", "C", "D", "E"],
        false,
        "File Recovery — what do you want to do?"
    );
}
if (!mode) { new Notice("Cancelled."); return; }

// ═════════════════════════════════════════════════════════════════════════════
// MODE A — Recover deleted file
// ═════════════════════════════════════════════════════════════════════════════
if (mode === "A") {
    new Notice("⏳ Searching for deleted files in backups…", 3000);
    let raw;
    try { raw = await git("log --diff-filter=D --name-only --oneline -80"); }
    catch (e) { new Notice(`❌ Git error: ${e}`); return; }

    const items = [];
    let currentHash = "", currentMsg = "";
    for (const line of raw.trim().split('\n')) {
        if (!line.trim()) continue;
        if (/^[0-9a-f]{7,12} /.test(line)) {
            currentHash = line.slice(0, 7);
            currentMsg  = line.slice(8).trim();
        } else {
            items.push({ file: line.trim(), hash: currentHash, message: currentMsg });
        }
    }
    if (!items.length) { new Notice("No deleted files found in the last 80 backups."); return; }

    let chosen;
    if (presetVal) {
        chosen = presetVal;
    } else {
        const labels  = items.map(i => `📄 ${i.file.split('/').pop()}   ←   ${i.hash} — ${i.message}`);
        chosen  = await tp.system.suggester(labels, items, false, "Select the file to recover");
    }
    if (!chosen) { new Notice("Cancelled."); return; }

    let preview;
    try { preview = await git(`show ${chosen.hash}^:"${chosen.file}"`); }
    catch (e) { new Notice(`❌ Could not read version: ${e}`); return; }

    const ok = await confirmRestore(chosen.file.split('/').pop(), preview);
    if (!ok) { new Notice("Cancelled."); return; }

    try {
        await ensureParentDir(chosen.file);
        await app.vault.adapter.write(chosen.file, preview);
        new Notice(`✅ Recovered → ${chosen.file}`);
    } catch (e) { new Notice(`❌ Write error: ${e}`); }
}

// ═════════════════════════════════════════════════════════════════════════════
// MODE B — Restore past version of current file
// ═════════════════════════════════════════════════════════════════════════════
else if (mode === "B") {
    let activeFile;
    if (targetFile) {
        activeFile = app.vault.getAbstractFileByPath(targetFile);
    } else {
        activeFile = window._actionsSourceFile || app.workspace.getActiveFile();
    }
    delete window._actionsSourceFile;
    if (!activeFile) { new Notice("❌ No active note."); return; }

    const relPath = activeFile.path;
    let chosen;
    if (presetVal) {
        chosen = presetVal;
    } else {
        new Notice(`⏳ Loading history for "${activeFile.basename}"…`, 3000);
        let raw;
        try { raw = await git(`log --oneline -40 -- "${relPath}"`); }
        catch (e) { new Notice(`❌ Git error: ${e}`); return; }

        const commits = parseLog(raw);
        if (!commits.length) { new Notice(`No backups found for "${activeFile.basename}".`); return; }

        const labels  = commits.map(c => `🕐 ${c.hash} — ${c.message}`);
        chosen  = await tp.system.suggester(labels, commits, false, `Choose version to restore — "${activeFile.basename}"`);
    }
    if (!chosen) { new Notice("Cancelled."); return; }

    let preview;
    try { preview = await git(`show ${chosen.hash}:"${relPath}"`); }
    catch (e) { new Notice(`❌ Could not read version: ${e}`); return; }

    const ok = await confirmRestore(activeFile.basename, preview);
    if (!ok) { new Notice("Cancelled."); return; }

    try {
        await app.vault.modify(activeFile, preview);
        new Notice(`✅ Restored "${activeFile.basename}"  (${chosen.message})`);
    } catch (e) { new Notice(`❌ Write error: ${e}`); }
}

// ═════════════════════════════════════════════════════════════════════════════
// MODE C — Preview a past version (read-only)
// ═════════════════════════════════════════════════════════════════════════════
else if (mode === "C") {
    let activeFile;
    if (targetFile) {
        activeFile = app.vault.getAbstractFileByPath(targetFile);
    } else {
        activeFile = window._actionsSourceFile || app.workspace.getActiveFile();
    }
    delete window._actionsSourceFile;
    if (!activeFile) { new Notice("❌ No active note."); return; }

    const relPath = activeFile.path;
    let chosen;
    if (presetVal) {
        chosen = presetVal;
    } else {
        new Notice(`⏳ Loading history for "${activeFile.basename}"…`, 3000);
        let raw;
        try { raw = await git(`log --oneline -40 -- "${relPath}"`); }
        catch (e) { new Notice(`❌ Git error: ${e}`); return; }

        const commits = parseLog(raw);
        if (!commits.length) { new Notice(`No backups found for "${activeFile.basename}".`); return; }

        const labels  = commits.map(c => `🕐 ${c.hash} — ${c.message}`);
        chosen  = await tp.system.suggester(labels, commits, false, `Choose backup to preview — "${activeFile.basename}"`);
    }
    if (!chosen) { new Notice("Cancelled."); return; }

    let content;
    try { content = await git(`show ${chosen.hash}:"${relPath}"`); }
    catch (e) { new Notice(`❌ Git error: ${e}`); return; }

    const previewPath = `00_STAGING/git-preview-${activeFile.basename}-${chosen.hash}.md`;
    const header = `> [!NOTE] Read-only snapshot — ${activeFile.basename} @ \`${chosen.hash}\`\n> **${chosen.message}**\n> This is a temporary copy. Close and delete it when you are done.\n\n---\n\n`;
    try {
        await app.vault.adapter.write(previewPath, header + content);
        await app.workspace.openLinkText(previewPath, "", true);
        new Notice(`👁️ Preview opened in 00_STAGING/ — this is a copy, not the original file.`);
    } catch (e) { new Notice(`❌ Error: ${e}`); }
}

// ═════════════════════════════════════════════════════════════════════════════
// MODE D — Recover renamed/moved file
// ═════════════════════════════════════════════════════════════════════════════
else if (mode === "D") {
    new Notice("⏳ Searching for renamed or moved files…", 3000);
    let raw;
    try { raw = await git("log --diff-filter=R --name-status --oneline -80"); }
    catch (e) { new Notice(`❌ Git error: ${e}`); return; }

    const items = [];
    let currentHash = "", currentMsg = "";
    for (const line of raw.trim().split('\n')) {
        if (!line.trim()) continue;
        if (/^[0-9a-f]{7,12} /.test(line)) {
            currentHash = line.slice(0, 7);
            currentMsg  = line.slice(8).trim();
        } else if (/^R/.test(line)) {
            const parts = line.split('\t');
            if (parts.length >= 3) {
                items.push({ oldPath: parts[1].trim(), newPath: parts[2].trim(), hash: currentHash, message: currentMsg });
            }
        }
    }
    if (!items.length) { new Notice("No renamed or moved files found in the last 80 backups."); return; }

    let chosen;
    if (presetVal) {
        chosen = presetVal;
    } else {
        const labels = items.map(i =>
            `📦 ${i.oldPath.split('/').pop()} → ${i.newPath.split('/').pop()}   (${i.hash} — ${i.message})`
        );
        chosen = await tp.system.suggester(labels, items, false, "Select the file to restore at its original location");
    }
    if (!chosen) { new Notice("Cancelled."); return; }

    let preview;
    try { preview = await git(`show ${chosen.hash}^:"${chosen.oldPath}"`); }
    catch (e) { new Notice(`❌ Could not read version: ${e}`); return; }

    const ok = await confirmRestore(chosen.oldPath.split('/').pop(), preview);
    if (!ok) { new Notice("Cancelled."); return; }

    try {
        await ensureParentDir(chosen.oldPath);
        await app.vault.adapter.write(chosen.oldPath, preview);
        new Notice(`✅ Restored at original path → ${chosen.oldPath}`);
    } catch (e) { new Notice(`❌ Write error: ${e}`); }
}

// ═════════════════════════════════════════════════════════════════════════════
// MODE E — Browse a backup commit (read-only)
// ═════════════════════════════════════════════════════════════════════════════
else if (mode === "E") {
    new Notice("⏳ Loading backup list…", 3000);
    let raw;
    try { raw = await git("log --oneline -50"); }
    catch (e) { new Notice(`❌ Git error: ${e}`); return; }

    const commits = parseLog(raw);
    let chosen;
    if (presetVal) {
        chosen = presetVal;
    } else {
        const labels  = commits.map(c => `🕐 ${c.hash} — ${c.message}`);
        chosen  = await tp.system.suggester(labels, commits, false, "Select the backup to browse");
    }
    if (!chosen) { new Notice("Cancelled."); return; }

    let stat;
    try { stat = await git(`show ${chosen.hash} --stat --no-patch`); }
    catch (e) { new Notice(`❌ Git error: ${e}`); return; }

    const browsePath = `00_STAGING/git-browse-${chosen.hash}.md`;
    const content = `> [!NOTE] Backup summary — ${chosen.message}\n> Hash: \`${chosen.hash}\`\n> This file is read-only, generated by file-recover.\n\n\`\`\`\n${stat.trim()}\n\`\`\`\n`;
    try {
        await app.vault.adapter.write(browsePath, content);
        await app.workspace.openLinkText(browsePath, "", true);
        new Notice(`🔍 Backup summary opened in 00_STAGING/`);
    } catch (e) { new Notice(`❌ Error: ${e}`); }
}
%>
