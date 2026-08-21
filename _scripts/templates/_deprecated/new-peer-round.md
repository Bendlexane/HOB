<%*
// Shared helpers (cache-busted so edits to the lib take effect immediately).
const _lp = `${app.vault.adapter.basePath}/_scripts/lib/templater-utils.js`;
try { delete require.cache[_lp]; } catch (e) {}
const U = require(_lp);

// Save original file content so we can restore it after Templater writes
const _activeFile = window._actionsSourceFile || app.workspace.getActiveFile();
delete window._actionsSourceFile;
let _origContent = "";
if (_activeFile) {
    try { _origContent = await app.vault.read(_activeFile); } catch (e) {}
}

const activeFile = _activeFile;
if (!activeFile) {
    new Notice("❌ No active file — run this template from within a peer review folder.");
    return;
}
const path = activeFile.path;
const peerMatch = path.match(/^(09_PEER_REVIEWS\/[^/]+)/);
if (!peerMatch) {
    new Notice(`❌ Active file (${activeFile ? activeFile.path : "null"}) is not inside a peer review folder.`);
    return;
}
const basePath = peerMatch[1];
const dirname = basePath.split("/").pop();

const parentNotePath = `${basePath}/${dirname}.md`;
const parentFile = app.vault.getAbstractFileByPath(parentNotePath);
if (!parentFile) {
    new Notice("❌ Parent metadata folder note not found.");
    return;
}
const parentContent = await app.vault.read(parentFile);

// Extract metadata
let journal = "";
let msid = "";
let totalRounds = 1;
let title = "";
let authors = "";

const mJournal = parentContent.match(/\njournal:\s*(.*)/);
if (mJournal) journal = mJournal[1].trim().replace(/^['"]|['"]$/g, "");
const mMsid = parentContent.match(/\nmanuscript_id:\s*(.*)/);
if (mMsid) msid = mMsid[1].trim().replace(/^['"]|['"]$/g, "");
const mRounds = parentContent.match(/\ntotal_rounds:\s*(\d+)/);
if (mRounds) totalRounds = parseInt(mRounds[1].trim(), 10);
const mTitle = parentContent.match(/\ntitle:\s*(.*)/);
if (mTitle) title = mTitle[1].trim().replace(/^['"]|['"]$/g, "");
const mAuthors = parentContent.match(/\nauthors:\s*(.*)/);
if (mAuthors) authors = mAuthors[1].trim().replace(/^['"]|['"]$/g, "");

const nextRound = totalRounds + 1;
const deadline = await U.pickDate(`Round ${nextRound} deadline`);
if (!deadline) return;

new Notice(`⏳ Creating Peer Review Round ${nextRound}...`);

const roundPath = `${basePath}/round_${nextRound}`;
const folders = [
    roundPath,
    `${roundPath}/manuscript`,
    `${roundPath}/supplementary`,
    `${roundPath}/scripts`,
    `${roundPath}/figures`,
];
for (const folder of folders) {
    try { await app.vault.createFolder(folder); } catch (e) {}
}

// Do not create round_N.md, metadata and timeline are held in the parent note.

const folderMeta = {
    "manuscript": { sticker: "1f4d6", desc: "PDF of the manuscript as received from the journal (immutable).\nIf the journal provides numbered versions (v1, v2), keep them all.\nNever modify the original PDF — track versions instead." },
    "supplementary": { sticker: "1f4ce", desc: "Supplemental material accompanying the manuscript: extra tables, datasets, extended methods appendices, PRISMA/ARRIVE checklists, or any file the journal provided as supporting info." },
    "scripts": { sticker: "1f4bb", desc: "Scripts (R, Python, bash, etc.) used for analyses, simulations, or verification of the results presented in the manuscript.\nInclude a README or inline comments to make every analysis reproducible." },
    "figures": { sticker: "1f5bc-fe0f", desc: "Figures generated during the review: diagrams, plots, heatmaps, visual comparisons, screenshots of software output.\nDo NOT put the original manuscript figures here (they go in manuscript/)." },
};

async function upsertFolderNote(notePath, stickerCode, body) {
    const content = body ? `---\nsticker: emoji//${stickerCode}\n---\n\n${body}\n` : `---\nsticker: emoji//${stickerCode}\n---\n`;
    if (!app.vault.getAbstractFileByPath(notePath)) {
        await app.vault.create(notePath, content);
    }
}

for (const f of folders.slice(1)) {
    const meta = folderMeta[U.basename(f)];
    if (!meta) continue;
    for (const notePath of U.getStickerNoteTargets(f)) {
        await upsertFolderNote(notePath, meta.sticker, meta.desc);
    }
}

await U.refreshMakeMdPaths(folders.slice(1));

const reviewReport = `---
type: peer-review-report
manuscript_id: ${msid}
journal: ${journal}
round: round_${nextRound}
reviewer: Anonymous
${title ? `title: "${title.replace(/"/g, '\\"')}"` : ""}
${authors ? `authors: "${authors.replace(/"/g, '\\"')}"` : ""}
deadline: ${deadline}
recommendation:
---

# Peer Review Report — ${msid} (Round ${nextRound})

**Manuscript title:** ${title || "_not provided_"}

**Authors:** ${authors || "_not provided_"}

**Journal:** ${journal}

**Round:** Round ${nextRound}

**Reviewer:** Anonymous

## 1. Summary of the Manuscript

_Provide a summary._

## 2. Comments

_Provide your comments._

---

## 3. Recommendation

- [ ] Accept as is
- [ ] Accept with minor revisions
- [ ] Major revisions required
- [ ] Reject

**Rationale:**

_
`;

const reportPath = `${roundPath}/${dirname}_peer_review.md`;
try {
    await app.vault.create(reportPath, reviewReport);
} catch (e) {}

// Update metadata and timeline in the parent note
let updatedParent = parentContent;

const mRoundsCheck = parentContent.match(/\ntotal_rounds:\s*(\d+)/);
if (mRoundsCheck) {
    updatedParent = updatedParent.replace(/\ntotal_rounds:\s*\d+/, `\ntotal_rounds: ${nextRound}`);
} else {
    updatedParent = updatedParent.replace(/^---([\s\S]*?)---/, (m, fm) => `---${fm}total_rounds: ${nextRound}\n---`);
}

const mStatus = updatedParent.match(/\nreview_status:\s*.*/);
if (mStatus) {
    updatedParent = updatedParent.replace(/\nreview_status:\s*.*/, `\nreview_status: in_progress`);
} else {
    updatedParent = updatedParent.replace(/^---([\s\S]*?)---/, (m, fm) => `---${fm}review_status: in_progress\n---`);
}

const mDead = updatedParent.match(/\ndeadline:\s*.*/);
if (mDead) {
    updatedParent = updatedParent.replace(/\ndeadline:\s*.*/, `\ndeadline: ${deadline}`);
} else {
    updatedParent = updatedParent.replace(/^---([\s\S]*?)---/, (m, fm) => `---${fm}deadline: ${deadline}\n---`);
}

const newGantt = `\`\`\`mermaid
gantt
    title Review timeline (Round ${nextRound})
    dateFormat YYYY-MM-DD
    axisFormat %d %b

    Received: milestone, ${tp.date.now("YYYY-MM-DD")}, 0d
    Review period : ${tp.date.now("YYYY-MM-DD")}, ${deadline}
    Deadline: milestone, ${deadline}, 0d
\`\`\``;

updatedParent = updatedParent.replace(/```mermaid\s*\ngantt\n[\s\S]*?```/, newGantt);

await app.vault.modify(parentFile, updatedParent);

await app.workspace.openLinkText(reportPath.replace(/\.md$/, ""), "");
new Notice(`✅ Round ${nextRound} created successfully!`);

if (_activeFile && _origContent) {
    tp.hooks.on_all_templates_executed(async () => {
        try {
            await app.vault.modify(_activeFile, _origContent);
        } catch (e) {}
    });
}
tR = _origContent;
_%>
