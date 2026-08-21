<%*
// ══════════════════════════════════════════════════════════════════════
//  FIELDWORK GENERATOR
//  Creates the fieldwork workspace under 05_ADMIN/missions/
// ══════════════════════════════════════════════════════════════════════

// Shared helpers (cache-busted so edits to the lib take effect immediately).
const _lp = `${app.vault.adapter.basePath}/_scripts/lib/templater-utils.js`;
try { delete require.cache[_lp]; } catch (e) {}
const U = require(_lp);
const BT = U.BT;

// ─── sticker for this fieldwork ────────────────────────────────────────
const missionEmoji = "emoji//1f97e"; // 🥾 hikers/boots

// ─── STEP 1: Inputs ───────────────────────────────────────────────────
const fieldworkName = await tp.system.prompt("Fieldwork name / Objective");
if (!fieldworkName) { new Notice("❌ Fieldwork creation cancelled."); return; }

const location = await tp.system.prompt("Location (region, country)");
if (!location) { new Notice("❌ Fieldwork creation cancelled."); return; }

const startDate = await U.pickDate("Start date");
if (!startDate) { new Notice("❌ Fieldwork creation cancelled."); return; }

const endDate = await U.pickDate("End date");
if (!endDate) { new Notice("❌ Fieldwork creation cancelled."); return; }

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

// ─── STEP 2: Derived paths ────────────────────────────────────────────
const [year, month] = startDate.split("-");
const locSlug = location
  .toLowerCase()
  .normalize("NFD")
  .replace(/[̀-ͯ]/g, "")
  .replace(/[^a-z0-9]+/g, "_")
  .replace(/^_|_$/g, "");
const dirName  = `${year}-${month}_${locSlug}`;
const basePath = `05_ADMIN/missions/fieldwork/${dirName}`;

// ─── STEP 3: Folder structure ─────────────────────────────────────────
const folderConfig = [
  { path: "administration",   sticker: "emoji//1f4cb", desc: "Authorization forms, official correspondence, director sign-offs." },
  { path: "expenses",          sticker: "emoji//1f4b0", desc: "All receipts, invoices, hotel, transport, and travel notes needed for reimbursement." },
  { path: "expenses/receipts",  sticker: "emoji//1f9fe", desc: "Payment receipts: hotel, meals, registration fee." },
  { path: "expenses/invoices",  sticker: "emoji//1f4c4", desc: "Formal invoices from hotels, transport companies, conference registration." },
  { path: "expenses/hotel",     sticker: "emoji//1f3e8", desc: "Booking confirmation, check-in/out times, address, cancellation policy." },
  { path: "expenses/transport", sticker: "emoji//1f684", desc: "Booking confirmations, seat reservations, rental agreements; also physical tickets/boarding passes." },
  { path: "expenses/travel_notes", sticker: "emoji//1f4dd", desc: "Free-form travel diary: delays, logistics, practical observations (not scientific notes)." },
];

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

// ─── STEP 4: Build _mission.md content ───────────────────────────────
const projPath = linkedProj ? `01_PROJECTS/${linkedProj}` : "01_PROJECTS/CODE";
const warningText = linkedProj 
  ? `This file covers **fieldwork logistics and summary**. Collected materials, field notebooks, and photos belong in ${BT}01_PROJECTS/${linkedProj}${BT}.`
  : `This file covers **fieldwork logistics and summary**.`;

const missionContent =
  `---\n` +
  `sticker: ${missionEmoji}\n` +
  `type: fieldwork\n` +
  `location: "${location}"\n` +
  `date_start: ${startDate}\n` +
  `date_end: ${endDate}\n` +
  `fieldwork_name: "${fieldworkName}"\n` +
  `linked_project: ${linkedProj ? `"[[${projPath}]]"` : "null"}\n` +
  `estimated_cost_eur: ${costStr ?? "null"}\n` +
  `authorization_status: ${authStatus}\n` +
  `created: ${tp.date.now("YYYY-MM-DD")}\n` +
  `---\n\n` +
  `# 🥾 ${fieldworkName} — ${location}\n\n` +
  `> [!warning] File scope\n` +
  `> ${warningText}\n\n` +
  `---\n\n` +
  `## Quick Access\n\n` +
  `| Folder | Purpose |\n|---|---|\n` +
  `| [[administration/administration]] | Authorization forms, official correspondence, director sign-offs |\n` +
  `| [[expenses/expenses]] | All receipts, invoices, hotel, transport, and travel notes needed for reimbursement |\n` +
  `| [[expenses/hotel/hotel]] | Hotel booking confirmation, check-in/out times, address, cancellation policy |\n` +
  `| [[expenses/transport/transport]] | Booking confirmations, seat reservations, rental agreements; also physical tickets/boarding passes |\n` +
  `| [[expenses/travel_notes/travel_notes]] | Free-form travel diary: delays, logistics, practical observations |\n\n` +
  `---\n\n` +
  `## 🎯 Objectives & Target Species\n\n` +
  `- **Primary Goal:** \n` +
  `- **Target Taxa / Species:**\n` +
  `  - \n` +
  `- **Notes / Specific requests:**\n\n` +
  `---\n\n` +
  `## 🗺️ Sampling Sites & Locations\n\n` +
  `| Site ID | Location Name | Coordinates (Lat/Lon) | Description & Access Notes |\n` +
  `|---|---|---|---|\n` +
  `| | | | |\n\n` +
  `---\n\n` +
  `## 📋 Permits & Nagoya Protocol\n\n` +
  `- **Collection Permit Ref / Status:** \n` +
  `- **MTA / Nagoya Protocol compliance notes:** \n` +
  `- **Landowner authorization / Parks permission:** \n\n` +
  `---\n\n` +
  `## 🚗 Logistics & Transport\n\n` +
  `- **Accommodation Details:** \n` +
  `- **Transport / Vehicle:** \n` +
  `- **Emergency Contacts:** \n\n` +
  `---\n\n` +
  `## 🎒 Equipment Checklist\n\n` +
  `- [ ] GPS / Offline Maps\n` +
  `- [ ] Sampling bags / envelopes\n` +
  `- [ ] Silica gel\n` +
  `- [ ] Plant press / newspaper\n` +
  `- [ ] Notebook & permanent markers\n` +
  `- [ ] Camera / smartphone\n` +
  `- [ ] Pruning shears / trowel\n` +
  `- [ ] First aid kit\n\n` +
  `---\n\n` +
  `## 📦 Collected Samples\n\n` +
  `| Sample ID | Date | Taxon | Site / Location | Notes / Phenology |\n` +
  `|---|---|---|---|---|\n` +
  `| | | | | |\n\n` +
  `---\n\n` +
  `## 📅 Daily Journal\n\n` +
  `### Day 1 — [Date]\n` +
  `- \n\n` +
  `### Day 2 — [Date]\n` +
  `- \n\n` +
  `---\n\n` +
  `## ✅ Post-mission checklist\n\n` +
  `- [ ] Expense report submitted to administration\n` +
  `- [ ] Samples cataloged and integrated in the lab\n` +
  `- [ ] Metadata (coordinates, field notes) digitized\n`;

await app.vault.create(`${basePath}/_mission.md`, missionContent);
await U.refreshMakeMdPaths(touchedFolders);

await app.workspace.openLinkText(`${basePath}/_mission`, "");
new Notice(`✅ Fieldwork created: ${fieldworkName} — ${location}`);
%>
