<%*
// ══════════════════════════════════════════════════════════════════════
//  REGENERATE DAILY NOTE
//  Re-runs AI extraction on the stored programme and replaces ONLY
//  the "# Schedule Overview" and "# Session Breakdown" sections.
//  Everything else (Research Insights, Free Notes) preserved untouched.
// ══════════════════════════════════════════════════════════════════════

// Shared helpers (cache-busted so edits to the lib take effect immediately).
const _lp = `${app.vault.adapter.basePath}/_scripts/lib/templater-utils.js`;
try { delete require.cache[_lp]; } catch (e) {}
const U = require(_lp);

// ─── resolve paths ────────────────────────────────────────────────────
const folder      = tp.file.folder(true);
const missionPath = folder.split("/").slice(0, -1).join("/");
const progPath    = `${missionPath}/conference_material/programme.md`;

// ─── read programme ───────────────────────────────────────────────────
const progFile = app.vault.getAbstractFileByPath(progPath);
if (!progFile) {
  new Notice(`❌ Programme file not found at:\n${progPath}\nRegeneration aborted.`);
  return;
}
const progContent = await app.vault.read(progFile);
const programme   = progContent.replace(/^---[\s\S]*?---\n/, "").trim();

// ─── read current note frontmatter ────────────────────────────────────
const noteFile    = app.vault.getAbstractFileByPath(tp.file.path(true));
const noteContent = await app.vault.read(noteFile);

const dayMatch  = noteContent.match(/^day:\s*(\d+)/m);
const dateMatch = noteContent.match(/^date:\s*(\S+)/m);
if (!dayMatch || !dateMatch) {
  new Notice("❌ Could not read 'day' or 'date' from frontmatter. Aborting.");
  return;
}
const dayNum  = parseInt(dayMatch[1]);
const dateStr = dateMatch[1];

// ─── load .env config ─────────────────────────────────────────────────
const env = await U.loadEnv();
const AI_URL   = env.AI_URL   || "http://localhost:11434/api/generate";
const AI_MODEL = env.AI_MODEL || "gpt-oss:120b-cloud";

// ─── AI call ──────────────────────────────────────────────────────────
new Notice(`⏳ Regenerating Day ${dayNum} from programme…`);

const raw = await U.aiFetch({ url: AI_URL, model: AI_MODEL, prompt: U.dayExtractionPrompt(dayNum, dateStr, programme) });
const ex = U.extractJson(raw, { sessions: [], main_themes: [] });
const sessions = Array.isArray(ex.sessions) ? ex.sessions : [];

// ─── build replacement sections ───────────────────────────────────────
const { newSchedule, newBreakdown } = U.buildDaySections(dayNum, dateStr, sessions);

// ─── Replace sections in note ─────────────────────────────────────────
// Match until next H1 only (not H2+), so ## Talks is kept within Session Breakdown.
const scheduleRe  = /# Schedule Overview[\s\S]*?(?=\n# (?!#))/;
const breakdownRe = /# Session Breakdown[\s\S]*?(?=\n# (?!#))/;

let updated = noteContent;
if (scheduleRe.test(updated)) {
  updated = updated.replace(scheduleRe, newSchedule);
}
if (breakdownRe.test(updated)) {
  updated = updated.replace(breakdownRe, newBreakdown);
}

await app.vault.modify(noteFile, updated);
new Notice(`✅ Day ${dayNum} regenerated from updated programme.`);
%>
