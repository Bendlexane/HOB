<%*
// ══════════════════════════════════════════════════════════════════════
//  MISSION GENERATOR
//  Creates the full conference/workshop workspace under 05_ADMIN/missions/
//
//  Requirements:
//    - Templater plugin
//    - Ollama running at localhost:11434 (optional, for programme parsing)
//
//  Buttons in generated daily notes use:
//    - Buttons plugin (installed)
//    - Templater "Template Hotkeys" commands (Settings → Templater → Template Hotkeys):
//        add these 3 paths so they register as commands (they stay OUT of the
//        insert-template suggester because they live outside templates_folder):
//          _scripts/templates/record-session-toggle.md
//          _scripts/templates/regenerate-all-daily-notes.md
//          _scripts/templates/regenerate-daily-note.md
//        Templater names the command by chopping the first 11 chars (len of
//        "_templates/") off the path, so the button `action` lines are:
//          action Templater: Insert mplates/record-session-toggle
//          action Templater: Insert mplates/regenerate-all-daily-notes
//          action Templater: Insert mplates/regenerate-daily-note
// ══════════════════════════════════════════════════════════════════════

// Shared helpers (cache-busted so edits to the lib take effect immediately).
const _lp = `${app.vault.adapter.basePath}/_scripts/lib/templater-utils.js`;
try { delete require.cache[_lp]; } catch (e) {}
const U = require(_lp);
const CB = U.CB;
const BT = U.BT;

const env = await U.loadEnv();
const AI_URL   = env.AI_URL   || "http://localhost:11434/api/generate";
const AI_MODEL = env.AI_MODEL || "gpt-oss:120b-cloud";

// ─── random emoji for this mission ─────────────────────────────────────
const MISSION_EMOJIS = [
  "emoji//1f30d", // 🌍 globe
  "emoji//1f30e", // 🌎 americas
  "emoji//1f30f", // 🌏 asia
  "emoji//1f5fa", // 🗺️ world map
  "emoji//1f9ed", // 🧭 compass
  "emoji//2708",  // ✈️ airplane
  "emoji//1f6e9", // 🛩️ small airplane
  "emoji//1f6f0", // 🛰️ satellite
  "emoji//1f680", // 🚀 rocket
  "emoji//1f30c", // 🌌 milky way
  "emoji//1f33f", // 🌿 herb
  "emoji//1f341", // 🍁 maple leaf
  "emoji//1f490", // 💐 bouquet
  "emoji//1f331", // 🌱 seedling
  "emoji//1f3d4", // 🏔️ mountain
  "emoji//1f3de", // 🏞️ national park
  "emoji//1f30a", // 🌊 wave
  "emoji//2601",  // ☁️ cloud
  "emoji//2600",  // ☀️ sun
  "emoji//1f319", // 🌙 crescent moon
  "emoji//2b50",  // ⭐ star
  "emoji//1f4a0", // 💠 diamond
  "emoji//1f3f0", // 🏰 castle
  "emoji//1f3db", // 🏛️ classical building
  "emoji//1f3e0", // 🏠 house
  "emoji//1f3e2", // 🏢 office
  "emoji//1f3eb", // 🏫 school
  "emoji//1f3d6", // 🏖️ beach
];
const missionEmoji = MISSION_EMOJIS[Math.floor(Math.random() * MISSION_EMOJIS.length)];

// ─── STEP 1: Inputs ───────────────────────────────────────────────────
const eventName = await tp.system.prompt("Event name (conference, workshop, symposium…)");
if (!eventName) { new Notice("❌ Mission creation cancelled."); return; }

const location = await tp.system.prompt("Location (city, country)");
if (!location) { new Notice("❌ Mission creation cancelled."); return; }

const website = await tp.system.prompt("Conference website URL — leave blank if unknown") ?? "";

const startDate = await U.pickDate("Start date");
if (!startDate) { new Notice("❌ Mission creation cancelled."); return; }

const endDate = await U.pickDate("End date");
if (!endDate) { new Notice("❌ Mission creation cancelled."); return; }

const contribution =
  (await tp.system.prompt("Your contribution title (talk / poster) — blank if none")) || null;

let contributionType = null;
if (contribution) {
  contributionType = await tp.system.suggester(
    ["talk — oral presentation", "poster", "invited — invited speaker"],
    ["talk", "poster", "invited"],
    false,
    "Select contribution type"
  ) || "talk";
}

const projFolder = app.vault.getAbstractFileByPath("01_PROJECTS");
const projectList = projFolder
  ? projFolder.children.filter(c => c.children).map(c => c.name.replace(/^01_PROJECTS\//, ""))
  : [];
const linkedProj = projectList.length
  ? (await tp.system.suggester(
      [...projectList.map(p => `📁 ${p}`), "— skip, no linked project —"],
      [...projectList, null],
      false,
      "Select linked project"
    )) || null
  : (await tp.system.prompt("Project code (e.g. 2026_ARMERIA) — blank if none")) || null;

const costStr =
  (await tp.system.prompt("Estimated cost in EUR — blank if unknown")) || null;

const authStatus = await tp.system.suggester(
  [
    "pending   — authorization not yet received",
    "approved  — authorization confirmed",
    "reimbursed — expenses settled",
  ],
  ["pending", "approved", "reimbursed"],
  false,
  "Authorization status"
);

const programme =
  (await tp.system.prompt(
    "Paste the full conference programme — leave blank to skip Ollama processing",
    "",
    true
  )) || "";

// ─── clean up programme formatting ────────────────────────────────────
const cleanProg = programme
  .replace(/\r\n?/g, "\n")
  .replace(/\n{3,}/g, "\n\n")
  .replace(/\f/g, "\n")
  .replace(/\t{2,}/g, "\t")
  // split on common structural markers if text is one dense blob
  .replace(/(?<=\S)\s+(?=\d{1,2}:\d{2}\s*-)/g, "\n")
  .replace(/(?<=\S)\s+(?=(Venue|Room|Location|Chair|Chairs|Keynote|Invited|Session|Day\s+\d|Track|Workshop|Poster|Lunch|Break|Registration|Welcome|Opening|Closing|Coffee|Networking)\s*:)/gi, "\n")
  .replace(/(?<=\S)\s{2,}(?=[A-Z][a-z]+)/g, "\n")
  .replace(/[ \t]+/g, " ")
  .replace(/^\s+|\s+$/gm, "")
  .trim();

const programmeFormatted = cleanProg !== programme;
const finalProgramme = programmeFormatted ? cleanProg : programme;

if (programmeFormatted) {
  new Notice("Programme text reformatted for readability.");
}

// ─── STEP 2: Derived paths ────────────────────────────────────────────
const [year, month] = startDate.split("-");
const locSlug = location
  .toLowerCase()
  .normalize("NFD")
  .replace(/[̀-ͯ]/g, "")
  .replace(/[^a-z0-9]+/g, "_")
  .replace(/^_|_$/g, "");
const dirName  = `${year}-${month}_${locSlug}`;
const basePath = `05_ADMIN/missions/conferences/${dirName}`;

// ─── STEP 3: Folder structure ─────────────────────────────────────────
const folderConfig = [
  { path: "administration",   sticker: "emoji//1f4cb", desc: "Authorization forms, official correspondence, director sign-offs." },
  { path: "expenses",          sticker: "emoji//1f4b0", desc: "All receipts, invoices, hotel, transport, and travel notes needed for reimbursement." },
  { path: "expenses/receipts",  sticker: "emoji//1f9fe", desc: "Payment receipts: hotel, meals, registration fee." },
  { path: "expenses/invoices",  sticker: "emoji//1f4c4", desc: "Formal invoices from hotels, transport companies, conference registration." },
  { path: "expenses/hotel",     sticker: "emoji//1f3e8", desc: "Booking confirmation, check-in/out times, address, cancellation policy." },
  { path: "expenses/transport", sticker: "emoji//1f684", desc: "Booking confirmations, seat reservations, rental agreements; also physical tickets/boarding passes." },
  { path: "expenses/travel_notes", sticker: "emoji//1f4dd", desc: "Free-form travel diary: delays, logistics, practical observations (not scientific notes)." },
  { path: "awards_certificates",  sticker: "emoji//1f3c6", desc: "Participation certificates and awards received at this event. Tagged #certificate." },
  { path: "conference_material",  sticker: "emoji//1f4d1", desc: "Received materials only: programme, abstract booklet, handouts from other presenters." },
];

if (!linkedProj) {
  folderConfig.push({
    path: "presentations",
    sticker: "emoji//1f4ca",
    desc: "Slides, posters, and abstracts for this invited talk/presentation (since no project is linked)."
  });
}

const touchedFolders = [basePath];

for (const f of folderConfig) {
  const fPath = `${basePath}/${f.path}`;
  await app.vault.createFolder(fPath).catch(() => {});
  touchedFolders.push(fPath);

  const targets = U.getStickerNoteTargets(fPath);
  for (const notePath of targets) {
    await app.vault.create(
      notePath,
      `---\nsticker: ${f.sticker}\ncssclasses: [graph-hide]\n---\n\n${f.desc}`
    ).catch(() => {});
  }
}

// ─── create daily_notes overview + button ─────────────────────────────
const dailyNotesPath = `${basePath}/daily_notes`;
await app.vault.createFolder(dailyNotesPath).catch(() => {});
touchedFolders.push(dailyNotesPath);

const dailyNotesTargets = U.getStickerNoteTargets(dailyNotesPath);
for (const notePath of dailyNotesTargets) {
  await app.vault.create(
    notePath,
    `---\nsticker: emoji//1f4c5\ncssclasses: [graph-hide]\n---\n\nOne \`.md\` per conference day, extracted from \`conference_material/programme.md\` via AI. Each note contains a Mermaid Gantt schedule and session breakdown with time/speakers/notes.\n\nThe **🔄 Regenerate all** button re-extracts all days from the updated programme.\n\nThe **🎙 Record** button (one per talk, under ##### Handwritten Notes) records audio, transcribes with Whisper, and appends under that same heading.\n\n\`\`\`button\nname 🔄 Regenerate all from programme\ntype command\naction Templater: Insert mplates/regenerate-all-daily-notes\nid regen-all\n\`\`\`\n^button-regen-all\n`
  ).catch(() => {});
}

// ─── create _recordings for raw audio ────────────────────────────────
const recordingsPath = `${basePath}/_recordings`;
await app.vault.createFolder(recordingsPath).catch(() => {});
touchedFolders.push(recordingsPath);

const recordingsTargets = U.getStickerNoteTargets(recordingsPath);
for (const notePath of recordingsTargets) {
  await app.vault.create(
    notePath,
    `---\nsticker: emoji//1f3a4\ncssclasses: [graph-hide]\n---\n\nRaw \`.wav\` audio from conference talk recordings, saved automatically by \`transcribe_server.py\` when stopping a recording. Files are kept until transcription succeeds, then deleted.\n\n**To manually retry a failed transcription:** place the \`.wav\` here, then run \`python _scripts/automation/transcribe_server.py --retry [filename]\` (TODO: implement retry CLI).\n`
  ).catch(() => {});
}

// ─── STEP 4: Store programme ──────────────────────────────────────────
if (finalProgramme) {
  await app.vault
    .create(
      `${basePath}/conference_material/programme.md`,
      `---\ntype: conference_programme\nconference: ${eventName}\nlocation: ${location}\ndate_start: ${startDate}\ndate_end: ${endDate}\n---\n\n# ${eventName} — Full Programme\n\n${finalProgramme}\n`
    )
    .catch(() => {});
}

// ─── STEP 5: Write _mission.md ──────────────────────────────────────
// (content built in Step 8 after daily notes are generated)

// ─── STEP 6: Date range ───────────────────────────────────────────────
function parseYmd(s) {
  const [y, m, d] = s.split("-").map(Number);
  return { y, m, d };
}
const start = parseYmd(startDate);
const end = parseYmd(endDate);
const days = [];
for (
  let d = new Date(Date.UTC(start.y, start.m - 1, start.d));
  d <= new Date(Date.UTC(end.y, end.m - 1, end.d));
  d.setUTCDate(d.getUTCDate() + 1)
) {
  days.push(d.toISOString().split("T")[0]);
}

// ─── STEP 7: Generate daily notes ─────────────────────────────────────
for (let i = 0; i < days.length; i++) {
  const dateStr = days[i];
  const dayNum  = i + 1;

  let ganttRows  = "    Sessions : 09:00, 8h";
  let tableRows  = "_No sessions extracted — fill manually or use the Regenerate button._";
  let talksRows  = "\n_No sessions to take notes on._\n";

  if (finalProgramme) {
    const raw1 = await U.aiFetch({ url: AI_URL, model: AI_MODEL, prompt: U.dayExtractionPrompt(dayNum, dateStr, finalProgramme) });
    const ex = U.extractJson(raw1, { sessions: [], main_themes: [] });
    const sessions = Array.isArray(ex.sessions) ? ex.sessions : [];

    const active = sessions.filter(s => s.type !== "break");
    const all = [...active, ...sessions.filter(s => s.type === "break")];
    all.sort((a, b) => (a.time_start || "").localeCompare(b.time_start || ""));

    ganttRows = U.sessionGanttRows(active);
    tableRows = U.buildSessionTable(all);
    talksRows = U.buildTalksSection(sessions, dateStr);
  }

  const noteContent =
    `---\ntype: conference_daily_note\nconference: "${eventName}"\nlocation: "${location}"\ndate: ${dateStr}\nday: ${dayNum}\ntags:\n  - conference\n  - certificate\nstatus: active\n---\n\n` +
    `# Day ${dayNum} — ${dateStr}\n\n` +
    `> [!tip] Quick Actions\n> ${BT}button-rec-toggle-${dateStr}${BT} — Click to start recording; click again to stop & transcribe (requires transcribe server running)\n\n` +
    `# Schedule Overview\n\n${CB}mermaid\n${U.ganttInitBlock}\ngantt\n    title Day ${dayNum} Schedule\n    dateFormat HH:mm\n    axisFormat %H:%M\n\n    section Sessions\n${ganttRows}\n${CB}\n# Session Breakdown\n\n${tableRows}\n\n## Talks${talksRows}\n\n` +
    `# Research Insights\n\n## Interesting Methods\n-\n\n## Emerging Topics\n-\n\n## Potential Collaborations\n-\n\n## Ideas To Explore\n-\n\n` +
    `# Free Notes\n\n## Scientific Notes\n-\n\n## References\n-\n`;

  await app.vault
    .create(`${basePath}/daily_notes/${dateStr}_day_${dayNum}.md`, noteContent)
    .catch(() => {});
}

// ─── STEP 8: Build _mission.md content ───────────────────────────────
const scheduleRows = days
  .map((d, i) => `| Day ${i + 1} | ${d} | [[daily_notes/${d}_day_${i + 1}]] |`)
  .join("\n");

const projPath = linkedProj ? `01_PROJECTS/${linkedProj}` : "01_PROJECTS/CODE";
const presentationPath = linkedProj ? `[[01_PROJECTS/${linkedProj}/07_presentations/]]` : `[[presentations]]`;
const warningText = linkedProj 
  ? `This file covers **mission logistics only**. Abstracts, slides, and posters belong in ${BT}01_PROJECTS/${linkedProj}/07_presentations/${BT}. Do not store presentation files here.`
  : `This file covers **mission logistics only**. Abstracts, slides, and posters belong in [[presentations]]. Do not store presentation files here.`;

const presentationsRow = linkedProj ? "" : `| [[presentations/presentations]] | Slides, posters, and abstracts for this invited talk/presentation |\n`;

const missionContent =
  `---\n` +
  `sticker: ${missionEmoji}\n` +
  `type: mission\n` +
  `location: "${location}"\n` +
  `date_start: ${startDate}\n` +
  `date_end: ${endDate}\n` +
  `event_name: "${eventName}"\n` +
  `conference_website: "${website}"\n` +
  `contribution_name: ${contribution ? `"${contribution}"` : "null"}\n` +
  `contribution_type: ${contributionType ? `"${contributionType}"` : "null"}\n` +
  `linked_project: ${linkedProj ? `"[[${projPath}]]"` : "null"}\n` +
  `estimated_cost_eur: ${costStr ?? "null"}\n` +
  `authorization_status: ${authStatus}\n` +
  `created: ${tp.date.now("YYYY-MM-DD")}\n` +
  `---\n\n` +
  `# ${eventName} — ${location}\n\n` +
  `> [!warning] File scope\n` +
  `> ${warningText}\n\n` +
  `---\n\n` +
  `## Quick Access\n\n` +
  `| Folder | Purpose |\n|---|---|\n` +
  `| [[administration/administration]] | Authorization forms, official correspondence, director sign-offs |\n` +
  `| [[expenses/expenses]] | All receipts, invoices, hotel, transport, and travel notes needed for reimbursement |\n` +
  `| [[expenses/hotel/hotel]] | Hotel booking confirmation, check-in/out times, address, cancellation policy |\n` +
  `| [[expenses/transport/transport]] | Booking confirmations, seat reservations, rental agreements; also physical tickets/boarding passes |\n` +
  `| [[expenses/travel_notes/travel_notes]] | Free-form travel diary: delays, logistics, practical observations |\n` +
  `| [[awards_certificates/awards_certificates]] | Participation certificates and awards received at this event; tagged ${BT}#certificate${BT} |\n` +
  `| [[conference_material/conference_material]] | Received materials only: programme, abstract booklet, handouts from other presenters |\n` +
  presentationsRow +
  `| [[daily_notes/daily_notes]] | Structured scientific daily notes, one per conference day |\n` +
  `| [[_recordings/_recordings]] | Raw audio recordings (${BT}.wav${BT}) of each recorded talk, kept until transcription succeeds |\n\n` +
  `**Conference website:** ${website || "_not provided_"}\n\n` +
  `---\n\n` +
  `## 🎯 Purpose\n\n` +
  `_Why are you attending? What do you present, what do you expect to learn, who do you plan to meet?_\n\n` +
  `---\n\n` +
  `## 📅 Schedule\n\n` +
  `| Day | Date | Daily note |\n|---|---|---|\n` +
  `${scheduleRows}\n\n` +
  `---\n\n` +
  `## 🎤 Contribution\n\n` +
  (contribution
    ? `- **Title:** ${contribution}\n- **Type:** ${contributionType}\n- **Files:** ${presentationPath}\n`
    : `_No contribution registered._\n`) +
  `\n---\n\n` +
  `## 👥 People to meet\n\n-\n`;

await app.vault.create(`${basePath}/_mission.md`, missionContent);
await U.refreshMakeMdPaths(touchedFolders);

await app.workspace.openLinkText(`${basePath}/_mission`, "");
new Notice(`✅ Mission created: ${eventName} — ${location} (${days.length} day${days.length > 1 ? "s" : ""})`);
%>
