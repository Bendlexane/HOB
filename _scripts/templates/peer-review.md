<%*
// Shared helpers (cache-busted so edits to the lib take effect immediately).
const _lp = `${app.vault.adapter.basePath}/_scripts/lib/templater-utils.js`;
try { delete require.cache[_lp]; } catch (e) {}
const U = require(_lp);

// ─── 1. REQUIRED FIELDS ────────────────────────────────────────────────
// Save original file content so we can restore it after Templater writes
const _activeFile = app.workspace.getActiveFile();
let _origContent = "";
if (_activeFile) {
    try { _origContent = await app.vault.read(_activeFile); } catch (e) {}
}

const journal = await tp.system.prompt("Journal code (e.g. JSE, TAXON, BOT_J_LINN)");
if (!journal) return;

const msid = await tp.system.prompt("Manuscript ID (assigned by the journal)");
if (!msid) return;

const deadline = await U.pickDate("Review deadline");
if (!deadline) return;

const abstract = await tp.system.prompt(
    "Paste manuscript details (title, authors, and abstract) — the AI will extract them automatically:",
    "", true
);
if (!abstract) return;

new Notice("⏳ Extracting metadata from abstract via AI...");

const env = await U.loadEnv();
const AI_URL = env.AI_URL || "http://localhost:11434/api/generate";
const AI_MODEL = env.AI_MODEL || "gpt-oss:120b-cloud";

let manuscriptTitle = "";
let authorsStr = "";
let cleanAbstract = "";
const raw = await U.aiFetch({
    url: AI_URL,
    model: AI_MODEL,
    prompt: `${abstract.slice(0, 8000)}`,
    system: `Extract the manuscript title, author list, and clean abstract from the text below.
Format each author as "Surname, First" (e.g. "Garcia Lopez, Maria").
Return ONLY valid JSON — no other text:
{"title": "...", "authors": "Surname1, First1, Surname2, First2, ...", "abstract": "..."}`
});
try {
    const m = raw.match(/\{[\s\S]*\}/);
    if (m) {
        const p = JSON.parse(m[0]);
        manuscriptTitle = p.title || "";
        authorsStr = p.authors || "";
        cleanAbstract = p.abstract || abstract;
    }
} catch (e) {
    if (raw) new Notice("⚠️ Failed to parse AI response as JSON");
}
if (!manuscriptTitle) new Notice("⚠️ AI extraction returned empty. Fill manually later.");

// ─── 2. FOLDER STRUCTURE ──────────────────────────────────────────────
// Each round (round_1, round_2, ...) is self-contained.
// Only _project.md (frontmatter + task list) at the project root.
//
// round_1/ — first review round (major revision → round_2, etc.)
//
//   manuscript/
//     PDF of the manuscript as received from the journal (immutable).
//     If the journal provides numbered versions (v1, v2), keep them all.
//     Never modify the original PDF — track versions instead.
//
//   supplementary/
//     Supplemental material accompanying the manuscript: extra tables,
//     datasets, extended methods appendices, PRISMA/ARRIVE checklists,
//     or any file the journal provided as supporting info.
//
//   scripts/
//     Scripts (R, Python, bash, etc.) used for analyses, simulations,
//     or verification of the results presented in the manuscript.
//     Include a README or inline comments to make every analysis reproducible.
//
//   figures/
//     Figures generated during the review: diagrams, plots,
//     heatmaps, visual comparisons, screenshots of software output.
//     Do NOT put the original manuscript figures here (they go in manuscript/).

const dirname = `${tp.date.now("YYYY-MM-DD")}_${journal}_${msid}`;
const basePath = `09_PEER_REVIEWS/${dirname}`;

const folders = [
    `${basePath}`,
    `${basePath}/.space`,
    `${basePath}/round_1`,
    `${basePath}/round_1/manuscript`,
    `${basePath}/round_1/supplementary`,
    `${basePath}/round_1/scripts`,
    `${basePath}/round_1/figures`,
];
for (const folder of folders) {
    try { await app.vault.createFolder(folder); } catch (e) {}
}

try {
    await app.vault.create(
        `${basePath}/.space/def.json`,
        JSON.stringify({
            _joins: [],
            _contexts: [],
            _links: [],
            _sort: { field: "name", asc: true, group: false, recursive: false },
            _template: "",
            _templateName: "",
            defaultSticker: "",
            defaultColor: "",
            readMode: false,
            fullWidth: false,
        })
    );
} catch (e) {}

// ─── 3. FOLDER DESCRIPTIONS & STICKERS ────────────────────────────────
const folderMeta = {
    "round_1": { sticker: "1f504", desc: "Each round is self-contained. Contains sub-folders for manuscript, supplementary, scripts, and figures." },
    "manuscript": { sticker: "1f4d6", desc: "PDF of the manuscript as received from the journal (immutable).\nIf the journal provides numbered versions (v1, v2), keep them all.\nNever modify the original PDF — track versions instead." },
    "supplementary": { sticker: "1f4ce", desc: "Supplemental material accompanying the manuscript: extra tables, datasets, extended methods appendices, PRISMA/ARRIVE checklists, or any file the journal provided as supporting info." },
    "scripts": { sticker: "1f4bb", desc: "Scripts (R, Python, bash, etc.) used for analyses, simulations, or verification of the results presented in the manuscript.\nInclude a README or inline comments to make every analysis reproducible." },
    "figures": { sticker: "1f5bc-fe0f", desc: "Figures generated during the review: diagrams, plots, heatmaps, visual comparisons, screenshots of software output.\nDo NOT put the original manuscript figures here (they go in manuscript/)." },
};

async function upsertFolderNote(notePath, stickerCode, body) {
    const content = body ? `---\nsticker: emoji//${stickerCode}\n---\n\n${body}\n` : `---\nsticker: emoji//${stickerCode}\n---\n`;
    const existing = app.vault.getAbstractFileByPath(notePath);
    if (!existing) {
        await app.vault.create(notePath, content);
        return;
    }
    const cur = await app.vault.read(existing);
    if (!/^---[\s\S]*?---\n?/.test(cur)) {
        await app.vault.modify(existing, `---\nsticker: emoji//${stickerCode}\n---\n\n${cur}`);
        return;
    }
    const updated = cur.replace(/^---([\s\S]*?)---\n?/, (m, p1) => {
        const fm = /\nsticker:\s*/.test(`\n${p1}`)
            ? p1.replace(/\nsticker:\s*.*\n?/, `\nsticker: emoji//${stickerCode}\n`)
            : `${p1}\nsticker: emoji//${stickerCode}\n`;
        return `---${fm}---\n\n${body || ""}`;
    });
    await app.vault.modify(existing, updated);
}

for (const f of folders.slice(3)) {
    const meta = folderMeta[U.basename(f)];
    if (!meta) continue;
    for (const notePath of U.getStickerNoteTargets(f)) {
        await upsertFolderNote(notePath, meta.sticker, meta.desc);
    }
}

await U.refreshMakeMdPaths(folders.slice(3));

// ─── 4. METADATA note BODY ──────────────────────────────────────────
const projectContent = `---
sticker: emoji//1f50d
type: peer-review
journal: ${journal}
manuscript_id: ${msid}
${manuscriptTitle ? `title: "${manuscriptTitle.replace(/"/g, '\\"')}"` : ""}
${authorsStr ? `authors: "${authorsStr.replace(/"/g, '\\"')}"` : ""}
received_date: ${tp.date.now("YYYY-MM-DD")}
review_status: in_progress # Options: [in_progress, completed]
deadline: ${deadline}
submitted_date:
days_to_complete:
recommendation: # Options: [accept, minor_revision, major_revision, reject]
status: in_progress
total_rounds: 1
final_recommendation:
---

# Review: ${journal} ${msid}

## 📊 Status

\`\`\`mermaid
gantt
    title Review timeline (Round 1)
    dateFormat YYYY-MM-DD
    axisFormat %d %b

    Received: milestone, ${tp.date.now("YYYY-MM-DD")}, 0d
    Review period : ${tp.date.now("YYYY-MM-DD")}, ${deadline}
    Deadline: milestone, ${deadline}, 0d
\`\`\`
`;

try {
    const projFile = app.vault.getAbstractFileByPath(`${basePath}/${dirname}.md`);
    if (projFile) {
        await app.vault.modify(projFile, projectContent);
    } else {
        await app.vault.create(`${basePath}/${dirname}.md`, projectContent);
    }
} catch (e) {}

// ─── 5. PEER REVIEW REPORT IN ROUND_1 ────────────────────────────────
const reviewReport = `---
type: peer-review-report
manuscript_id: ${msid}
journal: ${journal}
round: first_round
reviewer: Anonymous
${manuscriptTitle ? `title: "${manuscriptTitle.replace(/"/g, '\\"')}"` : ""}
${authorsStr ? `authors: "${authorsStr.replace(/"/g, '\\"')}"` : ""}
deadline: ${deadline}
recommendation:
---

# Peer Review Report — ${msid}

**Manuscript title:** ${manuscriptTitle || "_not provided_"}

**Authors:** ${authorsStr || "_not provided_"}

**Journal:** ${journal}

**Round:** First round

**Reviewer:** Anonymous

## 1. Summary of the Manuscript

${cleanAbstract}

## 2. Comments

_Provide an overall assessment._

## 3. Major Comments

### 3.1

### 3.2

## 4. Minor Comments

| Page / Line | Section | Comment |
| ----------- | ------- | ------- |
|             |         |         |

## 5. Language and Typos

| Page / Line | Section | Comment |
| ----------- | ------- | ------- |
|             |         |         |

## 6. Literature and Citations

-

## 7. Reproducibility and Data Availability

-

---

## 8. Recommendation

- [ ] Accept as is
- [ ] Accept with minor revisions
- [ ] Major revisions required
- [ ] Reject

**Rationale:**

_
`;

const reportPath = `${basePath}/round_1/${dirname}_peer_review.md`;
try {
    if (!app.vault.getAbstractFileByPath(reportPath)) {
        await app.vault.create(reportPath, reviewReport);
    }
} catch (e) {}

await app.workspace.openLinkText(`${basePath}/${dirname}`, "");
new Notice("✅ Peer review workspace created for " + journal + " " + msid);

// ─── 6. RESTORE ORIGINAL FILE ─────────────────────────────────────────
// Templater will write tR to the active file. Restore original content.
// Using the post-execution hook as the most reliable restore mechanism.
if (_activeFile && _origContent) {
    tp.hooks.on_all_templates_executed(async () => {
        try {
            await app.vault.modify(_activeFile, _origContent);
        } catch (e) {}
    });
}

tR = _origContent;
_%>
