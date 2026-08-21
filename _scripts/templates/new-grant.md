<%*
// ══════════════════════════════════════════════════════════════════════
//  NEW GRANT
//  Scaffolds a grant-writing workspace under 02_GRANTS/writing/, driven
//  by a call profile (_scripts/ops/grant_profiles/*.yaml).
//
//  Adding a future call = adding one profile YAML. No CORDIS/fit-score
//  engine here by design — see _meta/VAULT_ARCHITECTURE.md §5.
// ══════════════════════════════════════════════════════════════════════

const _lp = `${app.vault.adapter.basePath}/_scripts/lib/templater-utils.js`;
try { delete require.cache[_lp]; } catch (e) {}
const U = require(_lp);

const fs = require("fs");
const path = require("path");
const { exec } = require("child_process");

// ─── STEP 1: pick a call profile ───────────────────────────────────────
const profilesFolder = app.vault.getAbstractFileByPath("_scripts/ops/grant_profiles");
const profileFiles = (profilesFolder?.children || []).filter(f => f.extension === "yaml");
if (!profileFiles.length) {
  new Notice("❌ No call profile found in _scripts/ops/grant_profiles/.");
  return;
}
const profilePath = profileFiles.length === 1
  ? profileFiles[0].path
  : await tp.system.suggester(
      profileFiles.map(f => f.basename),
      profileFiles.map(f => f.path),
      false,
      "Select a call profile"
    );
if (!profilePath) { new Notice("❌ Grant creation cancelled."); return; }

const profile = await U.readYaml(profilePath);
if (!profile) { new Notice(`❌ Could not parse profile: ${profilePath}`); return; }

// ─── STEP 2: grant code ────────────────────────────────────────────────
const codeRaw = await tp.system.prompt("Grant code (format GRANT_YYYY_ACRONYM, e.g. GRANT_2026_MSCA)");
if (!codeRaw) { new Notice("❌ Grant creation cancelled."); return; }
const code = codeRaw.trim().toUpperCase().replace(/\s+/g, "_");
if (!/^GRANT_[0-9]{4}_[A-Z0-9_]+$/.test(code)) {
  new Notice("❌ Invalid code. Format: GRANT_YYYY_ACRONYM");
  return;
}
const existing = ["writing", "submitted", "active", "archive"]
  .map(s => app.vault.getAbstractFileByPath(`02_GRANTS/${s}/${code}`))
  .find(Boolean);
if (existing) {
  new Notice(`❌ ${code} already exists under 02_GRANTS/${existing.path.split("/")[1]}/`);
  return;
}

// ─── STEP 3: required fields ───────────────────────────────────────────
const title = (await tp.system.prompt("Grant title")) || code;

const agency = (await tp.system.prompt("Funding agency", profile.agency || "")) || profile.agency || null;
const callId = (await tp.system.prompt("Call ID", profile.call_id || "")) || profile.call_id || null;

const deadline = await U.pickDate("Submission deadline");
if (!deadline) { new Notice("❌ Grant creation cancelled."); return; }

// ─── STEP 4: optional fields (never block creation) ────────────────────
const amountRaw = (await tp.system.prompt("Amount requested in EUR — leave blank if unknown")) || "";
const amountRequested = amountRaw.trim() ? Number(amountRaw.trim().replace(/[^\d.]/g, "")) : null;
const hostInstitution = (await tp.system.prompt("Host institution — leave blank if unknown")) || null;
const supervisor = (await tp.system.prompt("Supervisor — leave blank if unknown")) || null;

// ─── STEP 5: base paths ─────────────────────────────────────────────────
const basePath = `02_GRANTS/writing/${code}`;
const partBPath = `${basePath}/part_b`;
const touchedFolders = [basePath];

for (const p of [basePath, partBPath, `${basePath}/notes`, `${basePath}/official_docs`]) {
  await app.vault.createFolder(p).catch(() => {});
  touchedFolders.push(p);
}

// ─── STEP 6: Part B — reuse an existing template, or generate a stub ───
const partBChoice = await tp.system.suggester(
  [
    "⏭️ Skip — generate a minimal Part B stub",
    "📄 Import existing LaTeX (.tex/.cls) from a folder",
    "📝 Convert Word document(s) (.docx) to LaTeX",
  ],
  ["skip", "copy", "convert"],
  false,
  "Part B source"
);

// { label, vaultPath } — used later to link Part B files from _grant.md
const partBFiles = [];

async function pickFolder(prompt) {
  return new Promise(resolve => {
    exec(
      `osascript -e 'POSIX path of (choose folder with prompt "${prompt}")'`,
      (err, stdout) => resolve(err ? null : stdout.trim().replace(/\/$/, ""))
    );
  });
}

function walkFiles(dir, extensions, out = []) {
  let entries = [];
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return out; }
  for (const e of entries) {
    if (e.name.startsWith(".")) continue;
    const full = path.join(dir, e.name);
    if (e.isDirectory()) walkFiles(full, extensions, out);
    else if (extensions.includes(path.extname(e.name).toLowerCase())) out.push(full);
  }
  return out;
}

if (partBChoice === "copy") {
  const srcDir = await pickFolder("Select the folder containing your Part B LaTeX (.tex/.cls/.sty/.bib) files…");
  if (srcDir) {
    const found = walkFiles(srcDir, [".tex", ".cls", ".sty", ".bib"]);
    for (const f of found) {
      const destName = path.basename(f);
      const destPath = `${partBPath}/${destName}`;
      try {
        const content = fs.readFileSync(f, "utf8");
        await app.vault.create(destPath, content);
        if (destName.toLowerCase().endsWith(".tex")) partBFiles.push({ label: destName, vaultPath: destPath });
      } catch (e) {}
    }
    if (!found.length) new Notice("⚠️ No .tex/.cls files found in that folder — generating stub instead.");
  }
}

if (partBChoice === "convert") {
  const srcDir = await pickFolder("Select the folder containing your Part B Word (.docx) file(s)…");
  if (srcDir) {
    const found = walkFiles(srcDir, [".docx"]);
    const pandoc = "/opt/homebrew/bin/pandoc";
    for (const f of found) {
      const destName = path.basename(f, path.extname(f)) + ".tex";
      const destAbsPath = path.join(app.vault.adapter.basePath, partBPath, destName);
      try {
        await new Promise((resolve, reject) => {
          exec(`"${pandoc}" "${f}" -o "${destAbsPath}"`, { shell: true }, (err, _out, stderr) =>
            err ? reject(stderr || err.message) : resolve()
          );
        });
        partBFiles.push({ label: destName, vaultPath: `${partBPath}/${destName}` });
      } catch (e) {
        new Notice(`❌ Pandoc conversion failed for ${path.basename(f)}: ${e}`);
      }
    }
    if (!found.length) new Notice("⚠️ No .docx files found in that folder — generating stub instead.");
  }
}

if (!partBFiles.length) {
  // Minimal stub, built from the profile's section list.
  const sections = profile.part_b1_sections || [];
  const includeLines = sections.map(s => `\\input{${s.id}}`).join("\n");
  const b2Sections = profile.part_b2_sections || [];
  const b2IncludeLines = b2Sections.map(s => `\\input{B2_${s.id}}`).join("\n");
  await app.vault.create(`${partBPath}/main.tex`,
    `% Part B — main file. Compile with pdflatex/latexmk.\n\\documentclass[11pt,a4paper]{article}\n\\usepackage[margin=2cm]{geometry}\n\\title{${title}}\n\\begin{document}\n% --- Part B1 (max ${profile.part_b1_max_pages || "?"} pages) ---\n${includeLines}\n${b2IncludeLines}\n\\end{document}\n`);
  partBFiles.push({ label: "main.tex", vaultPath: `${partBPath}/main.tex` });

  for (const s of sections) {
    await app.vault.create(`${partBPath}/${s.id}.tex`,
      `% ${s.title}\n% Page budget: ~${s.page_budget ?? "?"} pages\n% Weight: ${s.weight != null ? Math.round(s.weight * 100) + "%" : "?"}\n\n\\section{${s.title}}\n\n% TODO\n`);
    partBFiles.push({ label: `${s.title}`, vaultPath: `${partBPath}/${s.id}.tex` });
  }
  for (const s of b2Sections) {
    await app.vault.create(`${partBPath}/B2_${s.id}.tex`,
      `% ${s.title}\n% Page budget: ${s.page_budget != null ? "~" + s.page_budget + " pages" : "no strict limit"}\n\n\\section{${s.title}}\n\n% TODO\n`);
    partBFiles.push({ label: s.title, vaultPath: `${partBPath}/B2_${s.id}.tex` });
  }
  await app.vault.create(`${partBPath}/references.bib`, `% Export from Zotero (Better BibTeX) for ${code}\n`);
}

// ─── STEP 7: milestones, computed from the profile + chosen deadline ───
const deadlineMoment = moment(deadline, "YYYY-MM-DD");
const milestoneRows = (profile.milestones || [])
  .map(m => {
    const d = deadlineMoment.clone().subtract(m.offset_weeks, "weeks").format("YYYY-MM-DD");
    return `| -${m.offset_weeks} wk (${d}) | ${m.label} | |`;
  })
  .join("\n");

// ─── STEP 8: eligibility gate note ──────────────────────────────────────
const eligibilityItems = profile.eligibility || [];
const eligibilityChecklist = eligibilityItems
  .map(e => `- [ ] **${e.label}** <!-- ${e.id} -->`)
  .join("\n");
await app.vault.create(`${basePath}/_eligibility.md`,
  `---\nsticker: emoji//2705\n---\n\n# Eligibility — ${code}\n\n> Clear every gate **before** investing writing time.\n\n${eligibilityChecklist}\n`);

// ─── STEP 9: sticker notes for scaffolded subfolders ────────────────────
for (const p of [partBPath, `${basePath}/notes`, `${basePath}/official_docs`]) {
  const descByPath = {
    [partBPath]: "Part B LaTeX sources (narrative + CV/capacity annexes). Compile with latexmk/pdflatex.",
    [`${basePath}/notes`]: "Free-form working notes for this grant.",
    [`${basePath}/official_docs`]: "Official call documents: guide for applicants, work programme, templates, rules. Place PDFs here.",
  };
  const targets = U.getStickerNoteTargets(p);
  for (const notePath of targets) {
    await app.vault.create(notePath, `---\nsticker: emoji//1f4c1\ncssclasses: [graph-hide]\n---\n\n${descByPath[p]}`).catch(() => {});
  }
}

// ─── STEP 10: write _grant.md (manager note) ────────────────────────────
function yamlQuoted(s) { return `"${String(s || "").replace(/"/g, '\\"')}"`; }
function yamlStr(v) { return v == null ? "null" : yamlQuoted(v); }
function yamlNum(v) { return v == null || Number.isNaN(v) ? "null" : v; }

const eligibilityYaml = eligibilityItems
  .map(e => `  - id: ${e.id}\n    label: ${yamlQuoted(e.label)}\n    status: unknown`)
  .join("\n");

const partBLinks = partBFiles
  .map(f => `- [[${f.vaultPath}|${f.label}]]`)
  .join("\n");

const frontmatter =
  `---\nsticker: emoji//1f4b0\ntype: grant\ncode: ${code}\ntitle: ${yamlQuoted(title)}\nstatus: writing\nscheme: ${yamlQuoted(profile.scheme)}\nagency: ${yamlStr(agency)}\ncall_id: ${yamlStr(callId)}\nprofile: ${yamlQuoted(profilePath)}\ndeadline: ${deadline}\namount_requested: ${yamlNum(amountRequested)}\namount_funded: null\nperiod_start: null\nperiod_end: null\nhost_institution: ${yamlStr(hostInstitution)}\nsupervisor: ${yamlStr(supervisor)}\noutcome: null\ncreated: ${U.today()}\nlinked_projects: []\ndeliverables: []\neligibility:\n${eligibilityYaml}\n---\n`;

const body =
  `\n# ${title}\n\n` +
  `> **Grant manager** for \`${code}\` — your single cockpit: deadline, eligibility, milestones, Part B sections.\n\n` +
  "```dataviewjs\n" +
  `const fm = dv.current();\n` +
  `const dl = fm.deadline ? new Date(fm.deadline) : null;\n` +
  `if (dl) {\n  const days = Math.ceil((dl - new Date()) / 86400000);\n  dv.paragraph(\`### ⏳ **\${days}** days to deadline (\${fm.deadline})\`);\n} else dv.paragraph("### ⏳ No deadline set");\n` +
  "```\n\n" +
  `## ✅ Eligibility\nSee [[${basePath}/_eligibility|eligibility gate]] — clear it first.\n\n` +
  `## 📁 Official Documents\n- [[${basePath}/official_docs/|Official call documents & guidelines]] — place call texts, work programmes, templates, and rules here.\n\n` +
  `## 📅 Milestones\n| When | Milestone | Done |\n|---|---|---|\n${milestoneRows}\n\n` +
  `## ✍️ Part B sections\n${partBLinks}\n\n` +
  (profile.formatting ? `## 📐 Formatting\n${profile.formatting.map(f => `- ${f}`).join("\n")}\n` : "");

await app.vault.create(`${basePath}/_grant.md`, frontmatter + body);

// ─── STEP 11: wrap up ────────────────────────────────────────────────────
await U.refreshMakeMdPaths(touchedFolders);
await app.workspace.openLinkText(`${basePath}/_grant`, "");
new Notice(`✅ Grant created: ${code} — deadline ${deadline}`);
%>
