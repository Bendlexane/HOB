<%*
// ══════════════════════════════════════════════════════════════════════
//  LATEX ABSTRACT GENERATOR
//  Generates a LaTeX abstract file in a selected folder, pulling
//  authors and their affiliations from the database.
//
//  Requirements:
//    - Templater plugin
//    - Author registry at 04_PEOPLE/collaborators/_people-db.json
// ══════════════════════════════════════════════════════════════════════

// ─── STEP 1: Choose destination folder ───────────────────────────────
const folders = app.vault.getAllLoadedFiles()
  .filter(f => f.children && !f.path.startsWith('.') && !f.path.includes('.space'))
  .map(f => f.path)
  .sort();

const destFolder = await tp.system.suggester(folders, folders, false, "Select destination folder for the abstract");
if (!destFolder) return;

// ─── STEP 2: Read People database ────────────────────────────────────
const dbPath = "04_PEOPLE/collaborators/_people-db.json";
const dbFile = app.vault.getAbstractFileByPath(dbPath);
if (!dbFile) {
  new Notice(`❌ Author database not found at: ${dbPath}`);
  return;
}
const dbContent = await app.vault.read(dbFile);
let db = { people: [] };
try {
  db = JSON.parse(dbContent);
} catch (e) {
  new Notice(`❌ Failed to parse author database: ${e.message}`);
  return;
}

// ─── STEP 3: Select Authors ──────────────────────────────────────────
const selectedAuthors = [];
while (true) {
  const choices = ["— Done / Finish selecting —", ...db.people.map(p => p.display_name)];
  const pick = await tp.system.suggester(choices, choices, false, "Select author (select Done to finish)");
  if (!pick || pick === "— Done / Finish selecting —") {
    break;
  }
  const person = db.people.find(p => p.display_name === pick);
  if (person && !selectedAuthors.some(a => a.id === person.id)) {
    selectedAuthors.push(person);
    new Notice(`Added to abstract authors list: ${person.given_names} ${person.surname}`);
  }
}

if (selectedAuthors.length === 0) {
  new Notice("❌ No authors selected. Aborting.");
  return;
}

// ─── STEP 4: Prompt for Abstract Metadata ─────────────────────────────
const abstractTitle = await tp.system.prompt("Abstract title") || "Abstract Title";
const confName = await tp.system.prompt("Conference name") || "Conference Name";
const fileNameInput = await tp.system.prompt("File name (without extension, e.g. abstract_volos)") || "abstract";
const fileName = fileNameInput.endsWith(".tex") ? fileNameInput : `${fileNameInput}.tex`;

// ─── STEP 5: Process affiliations & format authors ───────────────────
const uniqueAffiliations = [];
const authorsList = [];

for (const author of selectedAuthors) {
  let chosenAffs = [];
  if (author.affiliations && author.affiliations.length > 0) {
    if (author.affiliations.length === 1) {
      chosenAffs = [author.affiliations[0]];
    } else {
      // Let user choose which affiliation(s) to use
      const choices = [
        "— Use all affiliations —",
        ...author.affiliations
      ];
      const selected = [];
      while (true) {
        const remainingChoices = choices.filter(c => c === "— Use all affiliations —" || !selected.includes(c));
        if (remainingChoices.length === 1 && remainingChoices[0] === "— Use all affiliations —") {
          break;
        }
        const title = `Select affiliation for ${author.given_names} ${author.surname} (select Done or Use all to finish)`;
        const pick = await tp.system.suggester(
          selected.length > 0 ? ["— Done / Finish selecting —", ...remainingChoices] : remainingChoices,
          selected.length > 0 ? ["— Done —", ...remainingChoices] : remainingChoices,
          false,
          title
        );
        if (!pick || pick === "— Done —") {
          break;
        }
        if (pick === "— Use all affiliations —") {
          selected.push(...author.affiliations);
          break;
        }
        selected.push(pick);
      }
      chosenAffs = selected.length > 0 ? selected : author.affiliations;
    }
  }

  const affNumbers = [];
  for (const aff of chosenAffs) {
    let idx = uniqueAffiliations.indexOf(aff);
    if (idx === -1) {
      uniqueAffiliations.push(aff);
      idx = uniqueAffiliations.length - 1;
    }
    affNumbers.push(idx + 1);
  }
  
  const name = `${author.given_names} ${author.surname}`;
  const affSup = affNumbers.length > 0 ? `^{${affNumbers.join(",")}}` : "";
  authorsList.push(`${name}$${affSup}$`);
}

let authorsTex = "";
if (authorsList.length > 0) {
  if (authorsList.length === 1) {
    authorsTex = authorsList[0];
  } else {
    authorsTex = authorsList.slice(0, -1).join(", ") + " and " + authorsList[authorsList.length - 1];
  }
}

const affiliationsTex = uniqueAffiliations.map((aff, i) => {
  return `\\textsuperscript{${i + 1}}${aff}`;
}).join("\\\\\n    ");

// ─── STEP 6: Choose LaTeX Template ───────────────────────────────────
const templateChoices = [
  "Standard LaTeX template (fully styled)",
  "Use a custom LaTeX template (.tex file from the vault)",
  "Paste a new custom LaTeX template (merge metadata using local LLM)",
  "Empty LaTeX file (blank file with only metadata headers)"
];

const templatePick = await tp.system.suggester(templateChoices, templateChoices, false, "Choose LaTeX template type");
if (!templatePick) return;

let texContent = "";

// Helper function to log error/doubts to HOB notification center
async function triggerNotificationCenterError(errorMsg) {
  try {
    const notiPath = "06_PLANNING/kpis/notifications.json";
    let notifications = [];
    try {
      const raw = await app.vault.adapter.read(notiPath);
      notifications = JSON.parse(raw);
      if (!Array.isArray(notifications)) notifications = [];
    } catch (e) {
      notifications = [];
    }

    const detailedLog = `Error/Doubts: ${errorMsg}\n\nMetadata:\n- Title: ${abstractTitle}\n- Conference: ${confName}\n- Authors: ${authorsTex}\n- Affiliations: ${affiliationsTex}`;
    const approveCmd = `node "_scripts/utils/create_standard_abstract.js" "${destFolder}" "${fileName}" "${abstractTitle.replace(/"/g, '\\"')}" "${confName.replace(/"/g, '\\"')}" "${authorsTex.replace(/"/g, '\\"')}" "${affiliationsTex.replace(/"/g, '\\"')}"`;

    const newNoti = {
      id: String(Date.now() + Math.random()),
      title: "LaTeX Merge Alert",
      message: `Failed to merge template: ${errorMsg.slice(0, 60)}... Create standard template instead?`,
      timestamp: Date.now(),
      read: false,
      sound: true,
      detailed_log: detailedLog,
      approve_cmd: approveCmd
    };

    notifications.push(newNoti);
    notifications = notifications.slice(-20);
    await app.vault.adapter.write(notiPath, JSON.stringify(notifications, null, 2));
    if (typeof window.__refreshDashboardNotifications === 'function') {
      window.__refreshDashboardNotifications();
    }
  } catch (err) {
    console.error("Failed to write to notification center", err);
  }
}

if (templatePick === "Standard LaTeX template (fully styled)") {
  texContent = `% !TEX program = lualatex
% ========================================================
% Conference Abstract — ${confName}
% Title: ${abstractTitle}
% ========================================================

\\documentclass[11pt]{article}
\\usepackage[a4paper, margin=1in]{geometry}

\\usepackage{libertinus-otf}
\\usepackage{microtype}
\\usepackage{eurosym}

\\usepackage{fancyhdr}

\\usepackage{xcolor}
\\definecolor{accent}{RGB}{58,115,184}
\\definecolor{ink}{RGB}{34,42,53}
\\definecolor{slate}{RGB}{92,103,115}

\\usepackage{hyperref}
\\hypersetup{
    colorlinks=true,
    breaklinks=true,
    urlcolor=accent,
    linkcolor=accent,
    anchorcolor=accent,
    citecolor=accent,
    pdftitle={${abstractTitle.replace(/[&_%$#]/g, '\\$&')}},
    pdfauthor={${selectedAuthors.map(a => `${a.given_names} ${a.surname}`).join(', ')}},
}

\\newcommand{\\orcidicon}{\\textsf{[ORCID]}}
\\IfFileExists{academicons.sty}{%
  \\usepackage{academicons}
  \\renewcommand{\\orcidicon}{\\aiOrcid}
}{}

\\setlength{\\parindent}{0pt}
\\setlength{\\parskip}{0.65em}

\\pagestyle{fancy}
\\fancyhf{}
\\renewcommand{\\headrulewidth}{0pt}
\\fancyfoot[C]{\\color{slate}\\small\\thepage}

\\begin{document}
\\color{ink}

\\begin{center}
    {\\LARGE\\bfseries\\color{accent} ${abstractTitle} \\par}
    \\vspace{1.2em}
    {\\large ${authorsTex} \\par}
    \\vspace{0.6em}
    {\\color{slate}\\small
    ${affiliationsTex}
    \\par}
\\end{center}

\\vspace{1.5em}

% ================= Body =================

% Write your abstract text here...

\\end{document}
`;
} else if (templatePick === "Use a custom LaTeX template (.tex file from the vault)") {
  const texFiles = app.vault.getFiles().filter(f => f.extension === "tex").map(f => f.path);
  if (texFiles.length === 0) {
    new Notice("❌ No .tex files found in the vault to use as a template.");
    return;
  }
  const chosenTemplatePath = await tp.system.suggester(texFiles, texFiles, false, "Select the .tex template to use");
  if (!chosenTemplatePath) return;

  const templateFile = app.vault.getAbstractFileByPath(chosenTemplatePath);
  const rawTemplate = await app.vault.read(templateFile);

  // Replace placeholders if present
  texContent = rawTemplate
    .replace(/\{\{title\}\}/gi, abstractTitle)
    .replace(/\[title\]/gi, abstractTitle)
    .replace(/\{\{authors\}\}/gi, authorsTex)
    .replace(/\[authors\]/gi, authorsTex)
    .replace(/\{\{affiliations\}\}/gi, affiliationsTex)
    .replace(/\[affiliations\]/gi, affiliationsTex)
    .replace(/\{\{conference\}\}/gi, confName)
    .replace(/\[conference\]/gi, confName);
} else if (templatePick === "Paste a new custom LaTeX template (merge metadata using local LLM)") {
  // Use Templater's prompt with multi_line set to true
  const pastedTemplate = await tp.system.prompt("Paste your custom LaTeX template", "", false, true);
  if (!pastedTemplate) return;

  // Pre-inject data into the pasted template
  const preInjectedTemplate = pastedTemplate
    .replace(/\{\{title\}\}/gi, abstractTitle)
    .replace(/\[title\]/gi, abstractTitle)
    .replace(/\{\{authors\}\}/gi, authorsTex)
    .replace(/\[authors\]/gi, authorsTex)
    .replace(/\{\{affiliations\}\}/gi, affiliationsTex)
    .replace(/\[affiliations\]/gi, affiliationsTex)
    .replace(/\{\{conference\}\}/gi, confName)
    .replace(/\[conference\]/gi, confName);

  // Send to Ollama
  new Notice("⏳ Asking AI to merge template metadata...");
  
  const sysPrompt = `You are an expert LaTeX assistant. Your sole task is to merge the provided metadata (Title, Conference Name, Authors, and Affiliations) into the user's LaTeX template, ensuring correct formatting, alignment, and LaTeX syntax.

Rules:
1. Maintain all packages, custom styling, document class definition, margins, and overall structure of the user's template.
2. Integrate the metadata seamlessly into the template's title/author blocks or custom formatting commands.
3. Do NOT invent, hallucinate, or add any dummy content, text, or extra papers/author details not explicitly provided in the metadata.
4. If you have any doubts, missing data, or formatting uncertainties, prefix your response with "DOUBT: [describe your doubts here]" before outputting the LaTeX code.
5. Ensure affiliations correspond correctly to authors based on the provided list.
6. Output ONLY the raw, complete LaTeX code (after the "DOUBT:" prefix if applicable). Do NOT wrap it in markdown blocks (e.g. do NOT use \`\`\`latex or \`\`\`). Do NOT include any explanations, warnings, or intro/outro text. The response must start directly with the LaTeX code (e.g. % !TEX or \\documentclass).`;

  const userPrompt = `Here is the metadata to integrate:
- Abstract Title: ${abstractTitle}
- Conference Name: ${confName}
- Authors with affiliation indexes: ${authorsTex}
- Affiliation Block:
${affiliationsTex}

Here is the LaTeX template (which may already have some metadata pre-injected):
----------------------------------------
${preInjectedTemplate}
----------------------------------------

Please merge the metadata into the template and return the complete, clean, and compilable LaTeX document.`;

  let responseText = "";
  try {
    const obsidian = require('obsidian');
    const response = await obsidian.requestUrl({
      url: "http://localhost:11434/api/generate",
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: "gpt-oss:120b-cloud",
        prompt: userPrompt,
        system: sysPrompt,
        stream: false
      })
    });
    
    if (response.status < 200 || response.status >= 300) {
      throw new Error(`HTTP status ${response.status}`);
    }
    
    const resJson = JSON.parse(response.text);
    responseText = (resJson.response || "").trim();
  } catch (err) {
    const errMsg = `Ollama connection failed: ${err.message}`;
    new Notice(`❌ ${errMsg}`);
    await triggerNotificationCenterError(errMsg);
    return; // Block creation
  }

  if (!responseText) {
    const errMsg = "Empty response received from Ollama.";
    new Notice(`❌ ${errMsg}`);
    await triggerNotificationCenterError(errMsg);
    return; // Block creation
  }

  // Check if LLM outputted doubts (starting with DOUBT:)
  if (responseText.startsWith("DOUBT:")) {
    const idx = responseText.indexOf("\n");
    let doubts = responseText;
    let actualContent = "";
    if (idx !== -1) {
      doubts = responseText.slice(0, idx).replace(/^DOUBT:\s*/i, "");
      actualContent = responseText.slice(idx + 1).trim();
    } else {
      doubts = responseText.replace(/^DOUBT:\s*/i, "");
    }
    const errMsg = `LLM flagged doubts: ${doubts}`;
    new Notice(`❌ ${errMsg}`);
    await triggerNotificationCenterError(errMsg);
    return; // Block creation
  }

  texContent = responseText;
} else {
  // Option 4: Empty template with metadata headers
  texContent = `% !TEX program = lualatex
% ========================================================
% Conference Abstract — ${confName}
% Title: ${abstractTitle}
% Authors: ${selectedAuthors.map(a => `${a.given_names} ${a.surname}`).join(', ')}
% ========================================================

% Write your custom LaTeX content here...
`;
}

// ─── STEP 7: Create the LaTeX file ───────────────────────────────────
const targetPath = `${destFolder}/${fileName}`;
try {
  await app.vault.create(targetPath, texContent);
  new Notice(`✅ LaTeX abstract created at: ${targetPath}`);
} catch (e) {
  new Notice(`❌ Failed to create abstract file: ${e.message}`);
}
%>
