<%*
// ══════════════════════════════════════════════════════════════════════
//  REGENERATE ALL DAILY NOTES
//  Re-runs AI extraction on the stored programme for every day and
//  replaces ONLY the "# Schedule Overview" and "# Session Breakdown"
//  sections in each daily note. Everything else is preserved.
//
//  Trigger from daily_notes/_overview.md button.
//  Requires: programme.md at conference_material/programme.md
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
  new Notice(`❌ Programme not found at:\n${progPath}`);
  return;
}
const progContent = await app.vault.read(progFile);
const programme   = progContent.replace(/^---[\s\S]*?---\n/, "").trim();

// ─── find daily notes ─────────────────────────────────────────────────
const dailyNotesFolder = app.vault.getAbstractFileByPath(folder);
if (!dailyNotesFolder) { new Notice(`❌ Folder not found: ${folder}`); return; }

const noteFiles = dailyNotesFolder.children.filter(
  f => f.name.endsWith(".md") && f.name.match(/^\d{4}-\d{2}-\d{2}_day_\d+\.md$/)
);
if (!noteFiles.length) { new Notice("❌ No daily notes found to regenerate."); return; }

// ─── load .env ────────────────────────────────────────────────────────
const env = await U.loadEnv();
const AI_URL   = env.AI_URL   || "http://localhost:11434/api/generate";
const AI_MODEL = env.AI_MODEL || "gpt-oss:120b-cloud";

// ─── regenerate each note ─────────────────────────────────────────────
new Notice(`⏳ Regenerating ${noteFiles.length} daily notes…`);

const scheduleRe  = /# Schedule Overview[\s\S]*?(?=\n# (?!#))/;
const breakdownRe = /# Session Breakdown[\s\S]*?(?=\n# (?!#))/;

let success = 0;
for (const nf of noteFiles) {
  const content = await app.vault.read(nf);
  const dayMatch  = content.match(/^day:\s*(\d+)/m);
  const dateMatch = content.match(/^date:\s*(\S+)/m);
  if (!dayMatch || !dateMatch) continue;

  const dayNum  = parseInt(dayMatch[1]);
  const dateStr = dateMatch[1];

  const raw = await U.aiFetch({ url: AI_URL, model: AI_MODEL, prompt: U.dayExtractionPrompt(dayNum, dateStr, programme) });
  const ex = U.extractJson(raw, { sessions: [], main_themes: [] });
  const sessions = Array.isArray(ex.sessions) ? ex.sessions : [];

  const { newSchedule, newBreakdown } = U.buildDaySections(dayNum, dateStr, sessions);

  let updated = content;
  if (scheduleRe.test(updated))  updated = updated.replace(scheduleRe, newSchedule);
  if (breakdownRe.test(updated)) updated = updated.replace(breakdownRe, newBreakdown);

  await app.vault.modify(nf, updated);
  success++;
}

new Notice(`✅ ${success}/${noteFiles.length} daily notes regenerated from updated programme.`);
%>
