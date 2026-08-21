<%*
// Shared helpers (cache-busted so edits to the lib take effect immediately).
// Aliased to local names so the rest of this template is unchanged.
const _lp = `${app.vault.adapter.basePath}/_scripts/lib/templater-utils.js`;
try { delete require.cache[_lp]; } catch (e) {}
const U = require(_lp);
const normalizeSpaces = U.normalizeSpaces;
const titleCase = U.titleCase;
const basename = U.basename;
const ensureMd = U.ensureMd;
const getStickerNoteTargets = U.getStickerNoteTargets;
const refreshMakeMdPaths = U.refreshMakeMdPaths;
const ensurePeopleDb = U.ensurePeopleDb;
const readPeopleDb = U.readPeopleDb;
const savePeopleDb = U.savePeopleDb;
const pickDate = U.pickDate;

// Load env helper from _scripts/.env
async function loadScriptsEnv() {
    try {
        const path = "_scripts/.env";
        const exists = await app.vault.adapter.exists(path);
        if (!exists) return {};
        const c = await app.vault.adapter.read(path);
        const e = {};
        for (const line of c.split("\n")) {
            const t = line.trim();
            if (t && !t.startsWith("#")) {
                const eq = t.indexOf("=");
                if (eq > 0) {
                    let val = t.slice(eq + 1).trim();
                    if (val.startsWith('"') && val.endsWith('"')) {
                        val = val.slice(1, -1);
                    }
                    e[t.slice(0, eq).trim()] = val;
                }
            }
        }
        return e;
    } catch {
        return {};
    }
}

// Success notification helper
async function addNotification(title, message) {
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

        const newNoti = {
            id: String(Date.now() + Math.random()),
            title: title,
            message: message,
            timestamp: Date.now(),
            read: false,
            sound: true
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

let success = false;
let code = "";
let title = "";
let errorObject = null;
const today = tp.date.now("YYYY-MM-DD");

try {
    // ─── 1. REQUIRED FIELDS ────────────────────────────────────────────────
    const codeRaw = await tp.system.prompt("Project code (format YYYY_PROJECT_KEYWORD, e.g. 2026_PLUMBAGO_PHYLO)");
    if (!codeRaw) {
        new Notice("❌ Project creation cancelled.");
        return;
    }
    code = codeRaw.trim().toUpperCase();
    if (!/^[0-9]{4}_[A-Z0-9]+_[A-Z0-9_]+$/.test(code)) {
        new Notice("❌ Invalid code. Format: YYYY_PROJECT_KEYWORD");
        return;
    }

    title = await tp.system.prompt("Project title (can differ from the final paper title)");
    if (!title) { new Notice("❌ Project creation cancelled."); return; }

const researchTypeOptions = [
    "Original article",
    "Methodological paper",
    "Review article",
    "Systematic review",
    "Meta-analysis",
    "Short communication",
    "Brief report",
    "Case report",
    "Perspective paper",
    "Opinion paper",
    "Editorial",
    "Letter to the editor",
    "Data paper"
];

const researchType = await tp.system.suggester(
    researchTypeOptions,
    researchTypeOptions,
    false,
    "Article format — used for KPI classification and template sections"
);
if (!researchType) { new Notice("❌ Project creation cancelled."); return; }

const role = await tp.system.suggester(
    [
        "lead — I lead this project (first author)",
        "coauthor — I contribute to someone else's project",
        "supervisor — I supervise (PI / last author)"
    ],
    ["lead", "coauthor", "supervisor"],
    false,
    "Your role"
);
if (!role) { new Notice("❌ Project creation cancelled."); return; }

const authorsTotalStr = await tp.system.prompt("Total expected authors including yourself", "2");
const authorsTotal = parseInt(authorsTotalStr);
if (!Number.isInteger(authorsTotal) || authorsTotal < 1) {
    new Notice("❌ authors_total must be an integer >= 1");
    return;
}

// Load env and fetch Zotero journals with local fallback
let zoteroJournals = [];
try {
    const env = await loadScriptsEnv();
    const apiKey = env.ZOTERO_API_KEY;
    if (apiKey) {
        // Retrieve key info to get numeric user ID
        const keyResp = await fetch(`https://api.zotero.org/keys/${apiKey}`, {
            headers: { "Zotero-API-Version": "3" }
        });
        if (keyResp.ok) {
            const keyInfo = await keyResp.json();
            const numericUserId = keyInfo.userID;
            if (numericUserId) {
                const itemsResp = await fetch(`https://api.zotero.org/users/${numericUserId}/items?itemType=journalArticle&limit=100`, {
                    headers: {
                        "Zotero-API-Key": apiKey,
                        "Zotero-API-Version": "3"
                    }
                });
                if (itemsResp.ok) {
                    const items = await itemsResp.json();
                    const journalsSet = new Set();
                    for (const item of items) {
                        const j = item.data?.publicationTitle;
                        if (j && j.trim()) {
                            journalsSet.add(j.trim());
                        }
                    }
                    zoteroJournals = Array.from(journalsSet).sort((a, b) => a.localeCompare(b, "en", { sensitivity: "base" }));
                }
            }
        }
    }
} catch (e) {
    console.error("Zotero API fetch failed, falling back to local files", e);
}

if (zoteroJournals.length === 0) {
    try {
        const litFiles = app.vault.getMarkdownFiles().filter(f => f.path.startsWith("03_KNOWLEDGE/literature/"));
        const journalsSet = new Set();
        for (const f of litFiles) {
            const cache = app.metadataCache.getFileCache(f);
            const journal = cache?.frontmatter?.journal;
            if (journal && journal.trim()) {
                journalsSet.add(journal.trim());
            }
        }
        zoteroJournals = Array.from(journalsSet).sort((a, b) => a.localeCompare(b, "en", { sensitivity: "base" }));
    } catch (e) {
        console.error("Local literature file scan failed", e);
    }
}

const journalOptions = [
    "TBD (To Be Determined)",
    "Enter custom journal (manual entry)...",
    ...zoteroJournals
];

const journalValues = [
    "TBD",
    "__CUSTOM__",
    ...zoteroJournals
];

const journalChoice = await tp.system.suggester(
    journalOptions,
    journalValues,
    false,
    "Target journal"
);

if (!journalChoice) {
    new Notice("❌ Project creation cancelled.");
    return;
}

let journalName = "";
if (journalChoice === "TBD") {
    journalName = "TBD";
} else if (journalChoice === "__CUSTOM__") {
    journalName = await tp.system.prompt("Target journal name", "");
    if (!journalName) {
        new Notice("❌ Project creation cancelled.");
        return;
    }
} else {
    journalName = journalChoice;
}

const journalFolder = journalName.replace(/[^a-zA-Z0-9_]+/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "").toLowerCase();

const projectStatusOptions = [
    "data_collection — collecting data, no paper yet",
    "drafting — data analysis and writing",
    "in_review — submitted and under review",
    "published — published, end of life cycle"
];
const projectStatus = await tp.system.suggester(
    projectStatusOptions,
    ["data_collection", "drafting", "in_review", "published"],
    false,
    "Current lifecycle phase — the Gantt chart anchors to this; only changes via archive_published.py after creation"
);
if (!projectStatus) { new Notice("❌ Project creation cancelled."); return; }

// Collect real start dates for every phase up to and including the current one.
// Asking for all phases (not just the current) is the only way to show accurate
// past bars in the Gantt when registering an already-running project.
// Blank = estimate that phase backward from p50 (fallback, less accurate).
const phaseStarts = {};
const _phaseInputLabel = {
    data_collection: "data collection",
    drafting: "drafting",
    in_review: "peer review"
};
const _phaseInputOrder = ["data_collection", "drafting", "in_review"];

// Phase 1 label depends on article type. null = no dc phase (Editorial, Letter).
const _phase1LabelMap = {
    "Original article":       "Data collection",
    "Short communication":    "Data collection",
    "Brief report":           "Data collection",
    "Case report":            "Documentation",
    "Data paper":             "Data curation",
    "Methodological paper":   "Development & validation",
    "Review article":         "Literature search",
    "Systematic review":      "Search & extraction",
    "Meta-analysis":          "Search & extraction",
    "Perspective paper":      "Concept development",
    "Opinion paper":          "Concept development",
    "Editorial":              null,
    "Letter to the editor":   null,
};
const _dcLabel = _phase1LabelMap[researchType] ?? "Data collection";
const hasDcPhase = _dcLabel !== null;

if (projectStatus !== "data_collection" && projectStatus !== "published") {
    const _upTo = _phaseInputOrder.indexOf(projectStatus);
    for (let _pi = 0; _pi <= _upTo; _pi++) {
        const _ph = _phaseInputOrder[_pi];
        // Skip dc date prompt entirely for article types without a dc phase.
        if (_ph === "data_collection" && !hasDcPhase) continue;
        const _label = _phaseInputLabel[_ph];
        const _isCurrent = _ph === projectStatus;
        const _hint = _isCurrent
            ? `When did ${_label} start? (Cancel/Skip = Today)`
            : `When did ${_label} start? (Cancel/Skip = Estimate)`;
        const _raw = await pickDate(_hint, _isCurrent ? today : "");
        if (_raw && /^\d{4}-\d{2}-\d{2}$/.test(_raw.trim())) {
            phaseStarts[_ph] = _raw.trim();
        }
    }
}

function isInitialToken(token) {
    const clean = normalizeSpaces(token).replace(/\./g, "");
    return /^[A-Za-zÀ-ÖØ-öø-ÿ]+$/.test(clean) && clean.length > 0 && clean.length <= 3;
}

function canonicalNameFromParts(surnameRaw, givenRaw) {
    const surname = titleCase(normalizeSpaces(surnameRaw));
    const given = titleCase(normalizeSpaces(givenRaw));
    if (!surname) return "";
    return given ? `${surname}, ${given}` : surname;
}

function parseAliases(raw) {
    if (Array.isArray(raw)) return raw.map(v => normalizeSpaces(String(v))).filter(Boolean);
    if (typeof raw === "string") return [normalizeSpaces(raw)].filter(Boolean);
    return [];
}

function uniqueByNormalized(items) {
    const seen = new Set();
    const out = [];
    for (const item of items) {
        const key = normalizeSpaces(item).toLowerCase();
        if (!key || seen.has(key)) continue;
        seen.add(key);
        out.push(item);
    }
    return out;
}

function canonicalFromRawName(raw) {
    const name = normalizeSpaces(raw);
    if (!name) return "";

    if (name.includes(",")) {
        const parts = name.split(",").map(p => normalizeSpaces(p));
        return canonicalNameFromParts(parts[0] || "", parts.slice(1).join(" "));
    }

    const tokens = name.split(" ").filter(Boolean);
    if (tokens.length === 1) return titleCase(tokens[0]);

    const first = tokens[0];
    const last = tokens[tokens.length - 1];
    const firstIsInitial = isInitialToken(first);
    const lastIsInitial = isInitialToken(last);

    // A. B. Carter / J. Smith -> Carter, A. B. / Smith, J.
    if (firstIsInitial && !lastIsInitial) {
        let i = 0;
        while (i < tokens.length && isInitialToken(tokens[i])) i += 1;
        const given = tokens.slice(0, i).join(" ");
        const surname = tokens.slice(i).join(" ");
        return canonicalNameFromParts(surname, given);
    }

    // Smith J. / Van Der Berg M. -> Smith, J. / Van Der Berg, M.
    if (!firstIsInitial && lastIsInitial) {
        let j = tokens.length - 1;
        while (j >= 0 && isInitialToken(tokens[j])) j -= 1;
        const surname = tokens.slice(0, j + 1).join(" ");
        const given = tokens.slice(j + 1).join(" ");
        return canonicalNameFromParts(surname, given);
    }

    // Given Surname -> Surname, Given (supports common compound surnames: De Luca, Von Berg...)
    const particles = new Set(["de", "del", "della", "di", "da", "d'", "von", "van", "la", "le"]);
    let surnameStart = tokens.length - 1;
    if (tokens.length >= 3) {
        const prev = tokens[tokens.length - 2].toLowerCase();
        if (particles.has(prev)) surnameStart = tokens.length - 2;
    }

    return canonicalNameFromParts(tokens.slice(surnameStart).join(" "), tokens.slice(0, surnameStart).join(" "));
}

function buildNameHints(people) {
    const surnames = new Set();
    const givens = new Set();
    for (const p of (people || [])) {
        const s = normalizeSpaces((p.surname || "").toLowerCase());
        if (s) surnames.add(s);
        const g = normalizeSpaces((p.given_names || "").toLowerCase());
        if (g) {
            g.split(" ").filter(Boolean).forEach(tok => givens.add(tok));
        }
    }
    return { surnames, givens };
}

function canonicalFromRawNameWithHints(raw, hints) {
    const base = canonicalFromRawName(raw);
    const name = normalizeSpaces(raw);
    if (!name || name.includes(",")) return base;

    const tokens = name.split(" ").filter(Boolean);
    if (tokens.length < 2) return base;

    const first = normalizeSpaces(tokens[0]).toLowerCase();
    const last = normalizeSpaces(tokens[tokens.length - 1]).toLowerCase();
    const firstIsInitial = isInitialToken(tokens[0]);
    const lastIsInitial = isInitialToken(tokens[tokens.length - 1]);
    if (firstIsInitial || lastIsInitial) return base;

    const firstIsKnownSurname = hints?.surnames?.has(first);
    const firstIsKnownGiven = hints?.givens?.has(first);
    const lastIsKnownSurname = hints?.surnames?.has(last);
    const lastIsKnownGiven = hints?.givens?.has(last);

    // Surname-first signal: known surname in first token and known given in last token
    if (firstIsKnownSurname && lastIsKnownGiven && !firstIsKnownGiven) {
        return canonicalNameFromParts(tokens.slice(0, -1).join(" "), tokens.slice(-1).join(" "));
    }

    // Given-first signal: known given in first token and known surname in last token
    if (firstIsKnownGiven && lastIsKnownSurname && !lastIsKnownGiven) {
        return canonicalNameFromParts(tokens.slice(-1).join(" "), tokens.slice(0, -1).join(" "));
    }

    // For 3+ tokens with no strong hint, prefer keeping first tokens as surname block (e.g., "Cañizares López María")
    if (tokens.length >= 3) {
        return canonicalNameFromParts(tokens.slice(0, -1).join(" "), tokens.slice(-1).join(" "));
    }

    return base;
}

function splitCoauthorInput(raw) {
    const text = normalizeSpaces(raw || "");
    if (!text) return [];

    // Prefer explicit separators to avoid ambiguity with "Surname, Given"
    if (text.includes(";")) {
        return text.split(";").map(s => normalizeSpaces(s)).filter(Boolean);
    }
    if (text.includes("\n")) {
        return text.split("\n").map(s => normalizeSpaces(s)).filter(Boolean);
    }

    // Fallback legacy behavior
    return text.split(",").map(s => normalizeSpaces(s)).filter(Boolean);
}

const peopleDbPath = "04_PEOPLE/collaborators/_people-db.json";

function buildPeopleCandidates(people) {
    return (people || [])
        .filter(p => p && p.display_name)
        .map(p => ({
            id: p.id || p.display_name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""),
            display_name: p.display_name,
            aliases: Array.isArray(p.aliases) ? p.aliases : [],
            affiliation: (Array.isArray(p.affiliations) && p.affiliations.length > 0)
                ? p.affiliations[0]
                : (p.affiliation || null)
        }))
        .sort((a, b) => a.display_name.localeCompare(b.display_name, "en", { sensitivity: "base" }));
}

const { file: peopleDbFile, data: peopleDb } = await readPeopleDb();
const peopleCandidates = buildPeopleCandidates(peopleDb.people);
const nameHints = buildNameHints(peopleDb.people);

const dbLookup = new Map();
for (const p of (peopleDb.people || [])) {
    const displayKey = normalizeSpaces(p.display_name || "").toLowerCase();
    if (displayKey) dbLookup.set(displayKey, p);
    for (const al of parseAliases(p.aliases)) {
        const aliasKey = normalizeSpaces(al).toLowerCase();
        if (aliasKey && !dbLookup.has(aliasKey)) dbLookup.set(aliasKey, p);
    }
}

let coauthorsList = [];
let addedNewPeople = 0;

let available = [...peopleCandidates];
while (true) {
    const labels = [
        "Stop selection (done)",
        "+ Add new coauthor...",
        ...available.map(c => c.affiliation ? `${c.display_name} — ${c.affiliation}` : c.display_name)
    ];
    const values = [
        "__DONE__",
        "__ADD_NEW__",
        ...available.map(c => c.id)
    ];
    const choice = await tp.system.suggester(
        labels,
        values,
        false,
        "Select a coauthor (pick one at a time, or choose '+ Add new coauthor...')"
    );
    if (!choice || choice === "__DONE__") {
        break;
    }
    if (choice === "__ADD_NEW__") {
        const name = await tp.system.prompt("New coauthor's name (Format: Surname, Given Names)", "");
        if (name) {
            const canonicalName = canonicalFromRawNameWithHints(name, nameHints);
            if (canonicalName) {
                const key = normalizeSpaces(canonicalName).toLowerCase();
                if (dbLookup.has(key)) {
                    new Notice(`⚠️ ${canonicalName} already exists in database. Selecting them.`);
                    const hit = dbLookup.get(key);
                    if (!coauthorsList.includes(hit.display_name)) {
                        coauthorsList.push(hit.display_name);
                        const availIdx = available.findIndex(c => c.id === hit.id);
                        if (availIdx !== -1) available.splice(availIdx, 1);
                    }
                    continue;
                }
                
                if (coauthorsList.includes(canonicalName)) {
                    new Notice(`⚠️ ${canonicalName} is already selected.`);
                    continue;
                }

                // Ask for email (optional)
                const email = await tp.system.prompt(`Email for ${canonicalName} (optional)`, "");
                // Ask for affiliation (optional)
                const affiliation = await tp.system.prompt(`Affiliation for ${canonicalName} (optional)`, "");
                
                // Add to database
                const surnameFirst = canonicalName.includes(",") ? canonicalName : `${canonicalName},`;
                const [surnameRaw, givenRaw = ""] = surnameFirst.split(",");
                const surname = normalizeSpaces(surnameRaw);
                const given_names = normalizeSpaces(givenRaw);
                const baseSlug = `${surname.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${given_names.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`
                    .replace(/-+/g, "-")
                    .replace(/^-+|-+$/g, "")
                    .replace(/-$/g, "");
                const slug = baseSlug || canonicalName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-+/g, "-").replace(/^-+|-+$/g, "");
                const rand = Math.random().toString(16).slice(2, 6);
                const canonicalSurname = surname.toLowerCase().trim();
                const canonicalGiven = given_names.toLowerCase().trim();

                const person = {
                    id: `${slug}-${rand}`,
                    slug,
                    display_name: canonicalName,
                    surname,
                    given_names,
                    canonical_name: canonicalGiven ? `${canonicalSurname}|${canonicalGiven}` : canonicalSurname,
                    aliases: [],
                    affiliations: affiliation ? [affiliation] : [],
                    orcid: null,
                    email: email || null,
                    notes: ""
                };

                peopleDb.people.push(person);
                addedNewPeople += 1;
                
                // Add to list of coauthors
                coauthorsList.push(canonicalName);
                
                // Save DB immediately
                await savePeopleDb(peopleDbFile, peopleDb);
                
                // Rebuild lookup to include newly added people
                dbLookup.set(normalizeSpaces(canonicalName).toLowerCase(), person);
                
                new Notice(`✅ Added ${canonicalName} to database and selected`);
            }
        }
    } else {
        const idx = available.findIndex(c => c.id === choice);
        if (idx !== -1) {
            coauthorsList.push(available[idx].display_name);
            available.splice(idx, 1);
        }
    }
}

if (coauthorsList.length === 0) coauthorsList = ["TBD"];

// ─── 2. AUTHORSHIP / CONTEXTUAL FIELDS ──────────────────────────────────
let position = 1;
let leadAuthor = "null";
let seniorAuthor = "";
let masterLocation = "local";
let authorshipNotes = '"Lead=1*; coauthors=2..n-1; senior=last"';

// Infer lead/senior from DB picks only (ordered input).
// Extra manually-added names are assumed to be middle authors.
const orderedAuthors = coauthorsList;
if (orderedAuthors.length > 0 && orderedAuthors[0] !== "TBD") {
    leadAuthor = `"${orderedAuthors[0].replace(/"/g, '\\"')}"`;
    if (role !== "supervisor") {
        seniorAuthor = `"${orderedAuthors[orderedAuthors.length - 1].replace(/"/g, '\\"')}"`;
    }
}

if (role === "coauthor") {
    position = 2;

    const ms = await tp.system.suggester(
        ["local — work in this folder", "external — paper on Google Doc / other's repo"],
        ["local", "external"],
        false,
        "Where the writing master lives — local creates a full folder tree; external creates only tracking files"
    );
    masterLocation = ms || "external";
}

if (role === "supervisor") {
    position = Math.max(2, authorsTotal);
}

if (role === "lead") {
    position = 1;
}

// ─── 3. FOLDER STRUCTURE + STICKERS ────────────────────────────────────
const basePath = `01_PROJECTS/${code}`;

const folderDefs = [
    { path: basePath,                                 sticker: "1f4c4", desc: "" },
    { path: `${basePath}/01_data`,                    sticker: "1f5c4-fe0f", desc: "Raw and processed datasets for this project. Sub-folders: `raw/` (immutable originals — git-ignored if heavy), `processed/` (post-QC data, reproducible from raw via scripts).\n\nDo NOT put analysis outputs or scripts here — those go in `02_analysis/outputs/` and `02_analysis/scripts/`." },
    { path: `${basePath}/01_data/raw`,                sticker: "1f5c4-fe0f", desc: "Immutable original data — never modify these files. Contains: `molecular/` (FASTQ reads, raw sequences), `morphological/` (field measurements, images), `cytological/` (flow cytometry files), `geographical/` (raw occurrence records, GPS exports). Git-ignored if heavy." },
    { path: `${basePath}/01_data/raw/molecular`,      sticker: "1f5c4-fe0f", desc: "Raw molecular data before any processing: untrimmed FASTQ reads, raw BAM files, unaligned sequences. Immutable." },
    { path: `${basePath}/01_data/raw/morphological`,  sticker: "1f5c4-fe0f", desc: "Raw morphological data: field measurement sheets, scanned forms, unprocessed images for landmarking. Immutable." },
    { path: `${basePath}/01_data/raw/cytological`,    sticker: "1f5c4-fe0f", desc: "Raw cytological data: unprocessed flow cytometry files (.fcs), raw karyotype images, original chromosome counts. Immutable." },
    { path: `${basePath}/01_data/raw/geographical`,   sticker: "1f5fa-fe0f", desc: "Raw geographic data: original occurrence records, GPS exports, downloaded shapefiles before cleaning or filtering. Immutable." },
    { path: `${basePath}/01_data/processed`,           sticker: "1f5c4-fe0f", desc: "Cleaned and curated data ready for analysis. Reproducible from `raw/` via scripts in `02_analysis/scripts/`. Contains: `molecular/`, `morphological/`, `cytological/`, `geographical/`." },
    { path: `${basePath}/01_data/processed/molecular`, sticker: "1f5c4-fe0f", desc: "Cleaned molecular data: trimmed reads, aligned FASTA, SNP matrices, filtered VCF, occupancy-filtered datasets." },
    { path: `${basePath}/01_data/processed/morphological`, sticker: "1f5c4-fe0f", desc: "Cleaned morphological tables: measurement CSVs with outliers removed, TPS landmark files, normalized character matrices." },
    { path: `${basePath}/01_data/processed/cytological`, sticker: "1f5c4-fe0f", desc: "Cleaned cytological data: analyzed flow cytometry results, chromosome counts with quality flags, ploidy assignments." },
    { path: `${basePath}/01_data/processed/geographical`, sticker: "1f5fa-fe0f", desc: "Cleaned geographic datasets: deduplicated occurrences, validated coordinates, filtered localities ready for SDMs or mapping." },
    { path: `${basePath}/02_analysis`,                sticker: "1f4c8", desc: "Scripts and computational results. `scripts/` (.R, .py, .sh, .nf — always versioned on git), `notebooks/` (.qmd, .Rmd), `outputs/` (intermediate results — git-ignored if heavy), `_analysis-log.md` (auto-updated by Quarto post-render hook — do NOT edit manually)." },
    { path: `${basePath}/02_analysis/scripts`,        sticker: "1f4c8", desc: "Versioned analysis scripts: .R, .py, .sh, .nf (Nextflow). Always tracked on git — never git-ignore scripts. Read from `01_data/processed/`, write results to `outputs/`." },
    { path: `${basePath}/02_analysis/notebooks`,      sticker: "1f4c8", desc: "Literate analysis documents: .qmd and .Rmd files with inline code, figures, and interpretation. Quarto renders to `outputs/`; the post-render hook updates `_analysis-log.md`." },
    { path: `${basePath}/02_analysis/outputs`,        sticker: "1f4c8", desc: "Intermediate analysis outputs: .RData, .pkl, model objects, run logs, filtered tables. Git-ignored if heavy. Reproducible from `01_data/` + `scripts/`." },
    { path: `${basePath}/02_analysis/outputs/caches`, sticker: "1f4c8", desc: "Pre-computed model objects for fast re-rendering: cached MCMC chains, pre-fitted models, large intermediate matrices. Git-ignored." },
    { path: `${basePath}/03_figures`,                 sticker: "1f5bc-fe0f", desc: "All figures for this project. `production/` (final TIFF/PDF for submission — TIFF git-ignored), `working/` (drafts, SVG, editable Inkscape/Illustrator files).\n\nDo NOT store data files or scripts here. Conference slides and posters belong in `07_presentations/`." },
    { path: `${basePath}/03_figures/production`,      sticker: "1f5bc-fe0f", desc: "Publication-ready figures: high-resolution TIFF/PDF labeled for the editor, exported at journal specifications. TIFF git-ignored. Do NOT edit after submission — create a new version if changes are needed." },
    { path: `${basePath}/03_figures/working`,         sticker: "1f5bc-fe0f", desc: "Work-in-progress figures: draft versions, alternative layouts, editable SVG/Inkscape/Illustrator files. These feed `production/` after approval." },
    { path: `${basePath}/04_writing`,                 sticker: "1f468-200d-1f4bb", desc: "Manuscript writing materials. `drafts/` (main .tex/.qmd), `_fragments/` (writing fragments), `coauthors/` (.docx with track changes), `supplementary/` (tables, appendices, extended methods), `references.bib` (project-specific BibTeX from Zotero).\n\nDo NOT put PDFs here (Zotero only). Do NOT use a global .bib file — one per project." },
    { path: `${basePath}/04_writing/drafts`,          sticker: "1f468-200d-1f4bb", desc: "Main manuscript: .tex or .qmd file, LaTeX class files, auxiliary configuration. Version history managed by git — do NOT create date-suffixed copies." },
    { path: `${basePath}/04_writing/coauthors`,       sticker: "1f468-200d-1f4bb", desc: "Coauthor contributions: .docx with track changes, PDF with annotations, feedback emails. Received versions go here; your responses go in `05_submission/[JOURNAL]/revN/resubmission/`." },
    { path: `${basePath}/04_writing/supplementary`,   sticker: "1f4ce", desc: "Manuscript supplementary materials: extended methods, supplementary tables (.xlsx), appendices, journal-specific checklists (PRISMA, ARRIVE). Submitted alongside the main manuscript." },
    { path: `${basePath}/04_writing/_fragments`,      sticker: "1f4dd", desc: "Writing fragments tied to this project: draft paragraphs, argument sketches, section outlines destined for the manuscript. One of the canonical fragment destinations in the vault." },
    { path: `${basePath}/05_submission`,              sticker: "1f4ee", desc: "Submission packages organized by journal. Each journal gets a sub-folder `[JOURNAL_CODE]/` with immutable round folders (`01_round/`, `02_round/`, ...). Each round is immutable — do NOT modify after submitting. Use `new-journal-round.md` to add a round." },
    { path: `${basePath}/05_submission/${journalFolder}`, sticker: "1f4ee", desc: `Submission materials for ${journalName}. Contains \`01_round/\` (first submission), \`02_round/\` (post-revision), etc. Each round is immutable — do NOT modify after sending.` },
    { path: `${basePath}/05_submission/${journalFolder}/01_round`, sticker: "1f4ee", desc: "First submission package: submitted manuscript (immutable), cover letter, supplementary materials, editor receipt. Do NOT modify after submission." },
    { path: `${basePath}/05_submission/${journalFolder}/02_round`, sticker: "1f4ee", desc: "Second round package (post-revision): revised manuscript, response to reviewers. Immutable after resubmission." },
    { path: `${basePath}/06_correspondence`,          sticker: "1f4ec", desc: "Communications related to this project. `reviewer_comments/` (excerpts, working response notes), `editor/` (emails auto-routed by IMAP when subject contains the project code).\n\nDo NOT manually copy emails here — `email_to_note.py` routes them automatically." },
    { path: `${basePath}/06_correspondence/${journalFolder}`, sticker: "1f4ec", desc: `Editorial correspondence for ${journalName}. Auto-populated by IMAP hook when the subject line contains the project code.` },
    { path: `${basePath}/06_correspondence/${journalFolder}/01_round`, sticker: "1f4ec", desc: "Correspondence for the first submission round: editor decision, reviewer reports. Auto-populated via IMAP hook." },
    { path: `${basePath}/06_correspondence/${journalFolder}/02_round`, sticker: "1f4ec", desc: "Correspondence for the second round: revised reviewer reports, final decision. Auto-populated." },
    { path: `${basePath}/07_presentations`,           sticker: "1f468-200d-1f3eb", desc: "Presentations based on this project's results. `abstracts/` (submitted/accepted conference abstracts), `posters/` (.pdf/.pptx, handouts).\n\nDo NOT put invited talks unlinked to this project — those go in `08_TEACHING/seminars/`. Conference logistics go in `05_ADMIN/missions/`." },
    { path: `${basePath}/07_presentations/abstracts`, sticker: "1f468-200d-1f3eb", desc: "Conference abstracts for this project: submitted text, submission form copy, acceptance notification. Named YYYY-MM_conference-acronym_abstract.md." },
    { path: `${basePath}/07_presentations/posters`,   sticker: "1f468-200d-1f3eb", desc: "Scientific posters: .pdf and .pptx source files, handout versions. Named YYYY-MM_conference-acronym_poster." },
    { path: `${basePath}/08_data-deposition`,         sticker: "1f3e6", desc: "Data deposits to public repositories. Sub-folders for `gbif/`, `genbank/`, `dryad/`, `bold/` plus `_deposition-log.md` (status, accession numbers, DOIs — auto-updated by CLI, do NOT edit manually).\n\nLog depositions: `data_deposition.py log [PROJECT_CODE] [REPO] --accession ... --records ...`" },
    { path: `${basePath}/08_data-deposition/gbif`,    sticker: "1f3e6", desc: "GBIF occurrence data deposit: DwC-Archive, Darwin Core mapping, dataset metadata. Feeds `data_depositions` SQLite after logging via CLI." },
    { path: `${basePath}/08_data-deposition/genbank`, sticker: "1f3e6", desc: "GenBank sequence submission: FASTA + feature tables, submission files, accession list. Log: `data_deposition.py log ... genbank --accession OR123456-OR123500`." },
    { path: `${basePath}/08_data-deposition/dryad`,   sticker: "1f3e6", desc: "Dryad data package: README, data manifest, cleaned datasets formatted for public deposition. Log DOI after acceptance." },
    { path: `${basePath}/08_data-deposition/bold`,    sticker: "1f3e6", desc: "BOLD barcode data: submission spreadsheet, voucher information, sequences in BOLD format." },
    { path: `${basePath}/09_meetings`,                sticker: "1f468-200d-1f469-200d-1f466-200d-1f466", desc: "Project meeting notes. Files named YYYY-MM-DD_topic.md with participants, decisions, and action items. Use the `meeting-note.md` Templater template for structured capture.\n\nDo NOT put conference session notes here — those go in `05_ADMIN/missions/[...]/daily_notes/`." },
];

async function upsertStickerNote(notePath, stickerCode) {
    const desiredFm = `---\nsticker: emoji//${stickerCode}\n---\n`;
    const existing = app.vault.getAbstractFileByPath(notePath);

    if (!existing) {
        await app.vault.create(notePath, desiredFm);
        return;
    }

    const content = await app.vault.read(existing);
    if (!/^---[\s\S]*?---\n?/.test(content)) {
        await app.vault.modify(existing, `${desiredFm}\n${content}`);
        return;
    }

    const updated = content.replace(/^---([\s\S]*?)---\n?/, (m, p1) => {
        if (/\nsticker:\s*/.test(`\n${p1}`)) {
            const p2 = p1.replace(/\nsticker:\s*.*\n?/, `\nsticker: emoji//${stickerCode}\n`);
            return `---${p2}---\n`;
        }
        return `---${p1}\nsticker: emoji//${stickerCode}\n---\n`;
    });

    await app.vault.modify(existing, updated);
}

let stickerApplied = 0;
let stickerFailed = 0;
const touchedFolders = [];

for (const f of folderDefs) {
    try { await app.vault.createFolder(f.path); } catch (e) {}
    touchedFolders.push(f.path);

    const targets = getStickerNoteTargets(f.path);
    for (const notePath of targets) {
        try {
            await upsertStickerNote(notePath, f.sticker);
            stickerApplied += 1;
        } catch (e) {
            stickerFailed += 1;
        }
    }
}

await refreshMakeMdPaths(touchedFolders);

// ─── 4.3 FOLDER DESCRIPTIONS ───────────────────────────────────────────────
async function upsertFolderDescription(folderPath, description) {
    if (!description) return;
    const targets = getStickerNoteTargets(folderPath);
    for (const notePath of targets) {
        const file = app.vault.getAbstractFileByPath(notePath);
        if (!file) continue;
        const content = await app.vault.read(file);
        if (content.includes(description)) continue;
        const updated = content.replace(/\n*$/, "") + `\n\n${description}\n`;
        await app.vault.modify(file, updated);
    }
}

for (const f of folderDefs) {
    if (f.desc) {
        await upsertFolderDescription(f.path, f.desc);
    }
}

// ─── 4. ACCESSORY FILES ───────────────────────────────────────────────────
// today is already defined globally at the top

try {
    await app.vault.create(
        `${basePath}/_log.md`,
`---
type: log
project: ${code}
code: ${code}
status_at_creation: ${projectStatus}
role: ${role}
authors_total: ${authorsTotal}
lead_author: ${leadAuthor}
created: ${today}
---

# Log — ${code}

> Chronological journal. Add entries with date at top, in reverse order.

---

## ${today}

_Project created._
`
    );
} catch (e) {}

try {
    await app.vault.create(
        `${basePath}/02_analysis/_analysis-log.md`,
`---
type: analysis-log
project: ${code}
---

# Analysis Log — ${code}

> Auto-updated by Quarto/R hook on run. You can add manual entries.

---
`
    );
} catch (e) {}

try { await app.vault.create(`${basePath}/04_writing/references.bib`, ""); } catch (e) {}

try {
    await app.vault.create(
        `${basePath}/08_data-deposition/_deposition-log.md`,
`---
type: deposition-log
project: ${code}
genbank:  { submitted: null, accessions: [], doi: null }
gbif:     { submitted: null, doi: null, records: null }
dryad:    { submitted: null, doi: null }
bold:     { submitted: null, accessions: [] }
---

# Deposition Log — ${code}
`
    );
} catch (e) {}

// ─── 4.5 AI PROJECT SUMMARY ──────────────────────────────────────────────
let projectSummary = "_Tell me about the project_";

const sysPrompt = "You are a scientific project assistant. Write a concise professional project summary (3-5 sentences) based on the user's rough notes. Cover: rationale, objectives, methods, expected outcomes. Use scientific tone. Plain text, no markdown headings.";

if (tp.app.plugins?.plugins?.["templater-obsidian"]) {
    const useAI = await tp.system.suggester(
        ["Yes — generate with AI (Ollama gemma4)", "No — I'll write it later"],
        ["yes", "no"],
        false,
        "3-5 sentence project summary written to _project.md — requires Ollama running locally"
    );
    if (useAI === "yes") {
        const rawNotes = await tp.system.prompt("Rough notes about the project — what, why, methods, expected outcomes (will be transformed into a formal summary by Ollama)", "");
        if (rawNotes) {
            try {
                const resp = await fetch("http://localhost:11434/api/generate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        model: "gemma4:latest",
                        system: sysPrompt,
                        prompt: `Write a project summary from these notes:\n\n${rawNotes}`,
                        stream: false,
                        options: { temperature: 0.3 }
                    })
                });
                const data = await resp.json();
                if (data.response) {
                    projectSummary = data.response.trim();
                }
            } catch (e) {
                new Notice(`❌ Ollama call failed: ${e.message}. Write summary later.`);
            }
        }
    }
}

// ─── 4.6 BAYESIAN GANTT CHART ────────────────────────────────────────────
// Phase durations are read from _scripts/ml/posteriors.json (regenerated nightly
// by update_posteriors.py). Falls back to priors.json mean if posteriors are
// absent (first-run case). Model: log-Normal with Beta-PERT-elicited NIG priors.
// See _meta/VAULT_ARCHITECTURE.md § "Bayesian Gantt prediction".
const phaseOrder = ["data_collection", "drafting", "in_review", "published"];

const phaseLabels = {
    data_collection: _dcLabel || "Data collection",
    drafting: "Analysis & writing",
    in_review: "Under review",
    published: "Published"
};
const phaseShort = { data_collection: "dc", drafting: "dr", in_review: "ir" };

const modelRole = role === "lead" ? "lead" : "not_lead";

async function readJsonFromVault(path) {
    const f = app.vault.getAbstractFileByPath(path);
    if (!f) return null;
    try {
        return JSON.parse(await app.vault.read(f));
    } catch (e) {
        return null;
    }
}

function pertExpected(p) {
    return Math.round((p.O + 4 * p.ML + p.P) / 6);
}

async function loadPhasePredictions(modelRole) {
    const posteriors = await readJsonFromVault("_scripts/ml/posteriors.json");
    if (posteriors && posteriors[modelRole]) {
        const c = posteriors[modelRole];
        return {
            dc: { p10: c.dc.p10_days, p50: c.dc.p50_days, p90: c.dc.p90_days, n: c.dc.n },
            dr: { p10: c.dr.p10_days, p50: c.dr.p50_days, p90: c.dr.p90_days, n: c.dr.n },
            ir: { p10: c.ir.p10_days, p50: c.ir.p50_days, p90: c.ir.p90_days, n: c.ir.n },
            source: "posterior"
        };
    }
    const priors = await readJsonFromVault("_scripts/ml/priors.json");
    if (priors && priors[modelRole]) {
        const c = priors[modelRole];
        return {
            dc: { p10: c.dc.O, p50: pertExpected(c.dc), p90: c.dc.P, n: 0 },
            dr: { p10: c.dr.O, p50: pertExpected(c.dr), p90: c.dr.P, n: 0 },
            ir: { p10: c.ir.O, p50: pertExpected(c.ir), p90: c.ir.P, n: 0 },
            source: "prior_mean"
        };
    }
    return {
        dc: { p10: 60, p50: 90, p90: 180, n: 0 },
        dr: { p10: 60, p50: 90, p90: 180, n: 0 },
        ir: { p10: 30, p50: 60, p90: 120, n: 0 },
        source: "hardcoded"
    };
}

const phasePred = await loadPhasePredictions(modelRole);

function addDays(dateStr, days) {
    const d = new Date(dateStr);
    d.setDate(d.getDate() + days);
    return d.toISOString().split("T")[0];
}

// activePhases: the phases shown in the Gantt. Editorial/Letter skip dc entirely.
const activePhases = hasDcPhase
    ? ["data_collection", "drafting", "in_review"]
    : ["drafting", "in_review"];

const currentIdx = activePhases.indexOf(projectStatus);
const phaseList = activePhases;
const starts = {};   // date strings for all three phases
const ends = {};     // date strings for all three phases

// Step 1: seed from user-provided real dates.
for (const [ph, dt] of Object.entries(phaseStarts)) {
    starts[ph] = dt;
}

// Step 2: fix active phase start, then project current + future phases forward.
const activeStart = starts[projectStatus] || today;
starts[projectStatus] = activeStart;

// For the current (active) phase, end = today + p50, NOT activeStart + p50.
// Rationale: if the project was registered after the phase already started (common for
// already-running projects), activeStart + p50 can fall in the past, causing the
// Mermaid "today" line to land visually inside the *next* phase bar — misleading.
// Using today + p50 reads as "expected time to completion from now", which is the
// useful Bayesian question regardless of how long the phase has already been running.
let cursor = today;
for (let i = currentIdx; i < phaseList.length; i++) {
    const ph = phaseList[i];
    const short = phaseShort[ph];
    if (!starts[ph]) starts[ph] = cursor;
    // Current phase ends today+p50; future phases chain from there.
    ends[ph] = addDays(i === currentIdx ? today : cursor, phasePred[short].p50);
    cursor = ends[ph];
}

// Step 3: for past phases, ends[ph] = starts[next phase] (exact if user gave it,
// or derived from chain). starts[ph] = user-provided or estimated backward via p50.
for (let i = currentIdx - 1; i >= 0; i--) {
    const ph = phaseList[i];
    const nextPh = phaseList[i + 1];
    const short = phaseShort[ph];
    ends[ph] = starts[nextPh];          // always defined at this point
    if (!starts[ph]) {
        starts[ph] = addDays(ends[ph], -phasePred[short].p50);
    }
}

const projStartDate = starts.data_collection || today;
const pubDate = ends.in_review;

let ganttItems = "";
phaseList.forEach((phase, i) => {
    const label = phaseLabels[phase];
    if (i < currentIdx) {
        ganttItems += `    ${label}  :done, ${starts[phase]}, ${ends[phase]}\n`;
    } else if (i === currentIdx) {
        const dur = phasePred[phaseShort[phase]].p50;
        ganttItems += `    ${label}  :crit, ${starts[phase]}, ${dur}d\n`;
    } else {
        const dur = phasePred[phaseShort[phase]].p50;
        ganttItems += `    ${label}  :${starts[phase]}, ${dur}d\n`;
    }
});
ganttItems += `    Published              :milestone, ${pubDate}, 0d\n`;

const ganttTheme = "";

const ganttBlock = `\`\`\`mermaid
${ganttTheme}
gantt
    title Project Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  %b %Y

    Project started       :milestone, ${projStartDate}, 0d
${ganttItems}\`\`\``;

const totalObs = phasePred.dc.n + phasePred.dr.n + phasePred.ir.n;
const sourceLabel = phasePred.source === "posterior"
    ? `posterior predictive (${totalObs} obs across role=${modelRole})`
    : phasePred.source === "prior_mean"
        ? "prior Beta-PERT mean (no posteriors yet)"
        : "hardcoded fallback (no priors found)";

const _tableRows = [];
if (hasDcPhase) {
    _tableRows.push(`| ${phaseLabels.data_collection} | ${phasePred.dc.p10} d | **${phasePred.dc.p50} d** | ${phasePred.dc.p90} d | ${phasePred.dc.n} |`);
}
_tableRows.push(`| Analysis & writing | ${phasePred.dr.p10} d | **${phasePred.dr.p50} d** | ${phasePred.dr.p90} d | ${phasePred.dr.n} |`);
_tableRows.push(`| Under review | ${phasePred.ir.p10} d | **${phasePred.ir.p50} d** | ${phasePred.ir.p90} d | ${phasePred.ir.n} |`);

const uncertaintyTable = [
    "| Phase | p10 | **p50** (Gantt) | p90 | n obs |",
    "|---|---|---|---|---|",
    ..._tableRows,
    "",
    `> Source: ${sourceLabel}. Model: log-Normal with Beta-PERT priors (BBM-flavored NIG; see [VAULT_ARCHITECTURE](../../_meta/VAULT_ARCHITECTURE.md#bayesian-gantt-prediction)).`,
    "",
    "> [!tip] Keeping predictions reliable",
    "> 1. **Update `status:` as you go** — move it to `drafting` when you start writing, to `in_review` on submission, to `published` on acceptance. The model learns from every transition.",
    "> 2. **Also set the matching `phase_*_start` date** — when you advance status, add the real start date in frontmatter (`phase_dr_start` for drafting, `phase_ir_start` for in_review). The 8:10 AM cron reads these to regenerate the Gantt correctly. Never edit the mermaid block directly — it will be overwritten.",
    "> 3. **Set `status: published` on acceptance** — the daily 8:00 cron archives the project automatically. Completed projects are what train the model.",
    "> 4. **Don't skip phases** — always go through `data_collection → drafting → in_review → published`. Skipping a phase means the model never learns that phase's duration.",
    "> 5. **Keep git auto-commit on** — the model extracts phase durations from the git history of `_project.md`. If `obsidian-git` doesn't commit, transitions are invisible to the model."
].join("\n");

const ganttChart = ganttBlock + "\n\n" + uncertaintyTable;

// ─── 4.7 COAUTHORS TABLE ────────────────────────────────────────────────
const coauthorTableRows = coauthorsList.map(name => {
    const key = normalizeSpaces(name).toLowerCase();
    const person = dbLookup.get(key);
    const affiliation = (person?.affiliations?.[0] || "—").replace(/\|/g, "\\|");
    const email = (person?.email || "—").replace(/\|/g, "\\|");
    return `| ${name.replace(/\|/g, "\\|")} | ${affiliation} | ${email} |`;
}).join("\n");

// ─── 5. WRITE _project.md (IDEMPOTENT) ──────────────────────────────────
function unquoteOrEmpty(v) {
    const s = normalizeSpaces(v || "");
    if (!s || s === "null") return "";
    return s.replace(/^"(.*)"$/, "$1");
}

function yamlQuoted(s) {
    return `"${String(s || "").replace(/"/g, '\\"')}"`;
}

const leadAuthorRaw = unquoteOrEmpty(leadAuthor);
const seniorAuthorRaw = unquoteOrEmpty(seniorAuthor);
const authorshipNotesRaw = unquoteOrEmpty(authorshipNotes);
const coauthorsYaml = (coauthorsList.length ? coauthorsList : ["TBD"])
    .map(n => `  - ${yamlQuoted(n)}`)
    .join("\n");

const projectContent = `---
sticker: emoji//1f4c4
code: ${code}
title: ${yamlQuoted(title)}
research_type: ${yamlQuoted(researchType)}
status: ${projectStatus}
role: ${role}
position: ${position}
authors_total: ${authorsTotal}
lead_author: ${leadAuthorRaw ? yamlQuoted(leadAuthorRaw) : "null"}
senior_author: ${seniorAuthorRaw ? yamlQuoted(seniorAuthorRaw) : ""}
master_location: ${masterLocation}
journal_target: ${yamlQuoted(journalName)}
linked_grant: null
coauthors:
${coauthorsYaml}
authorship_notes: ${yamlQuoted(authorshipNotesRaw || "Lead=1*; coauthors=2..n-1; senior=last")}
created: ${tp.date.now("YYYY-MM-DD")}
phase_dc_start: ${phaseStarts.data_collection ? yamlQuoted(phaseStarts.data_collection) : (projectStatus === "data_collection" ? yamlQuoted(today) : "null")}
phase_dr_start: ${phaseStarts.drafting ? yamlQuoted(phaseStarts.drafting) : "null"}
phase_ir_start: ${phaseStarts.in_review ? yamlQuoted(phaseStarts.in_review) : "null"}
phase_1_label: ${_dcLabel ? yamlQuoted(_dcLabel) : "null"}
---

# ${title}

## 📊 Current status

\`\`\`base
filters:
  and:
    - file.path: "${basePath}"
view: project-cockpit
\`\`\`

## 🎯 Project summary

${projectSummary}

## 📋 Timeline

${ganttChart}

## 👥 Coauthors

| Name | Affiliation | Email |
|------|-------------|-------|
${coauthorTableRows}

## 🔗 Quick links

- Chronological log: [[_log]]
- Analysis: [[02_analysis/_analysis-log]]
- Coauthors: [[04_writing/coauthors/_coauthors]]
- Submission: [[05_submission/${journalFolder}/01_round]]
- Correspondence: [[06_correspondence/${journalFolder}/01_round]]
- Supplementary: [[04_writing/supplementary/]]

## 📚 Project Literature

#### 📊 Literature by Category

*Chart of readings associated with this project grouped by category/tag.*

\`\`\`chartsview
type: Pie
data: |
  dataviewjs:
  const pages = dv.pages('"03_KNOWLEDGE/literature" or "00_STAGING"')
    .filter(p => p.project_code && (Array.isArray(p.project_code) ? p.project_code.includes(dv.current().code) : p.project_code == dv.current().code));
  const tagCounts = {};
  for (const p of pages) {
    const tags = p.file.tags || p.tags || [];
    for (const tag of tags) {
      const cleanTag = tag.replace(/^#/, "");
      tagCounts[cleanTag] = (tagCounts[cleanTag] || 0) + 1;
    }
  }
  return Object.entries(tagCounts).map(([tag, count]) => ({ category: tag, value: count }));
options:
  angleField: "value"
  colorField: "category"
  radius: 0.6
  legend:
    position: "bottom"
\`\`\`

#### 📋 Literature List

*Complete list of associated readings. Click on the title to open the Obsidian note, or click on Zotero to open Zotero.*

\`\`\`dataviewjs
this.container.style.maxHeight = "400px";
this.container.style.overflowY = "auto";

const pages = dv.pages('"03_KNOWLEDGE/literature" or "00_STAGING"')
  .filter(p => p.project_code && (Array.isArray(p.project_code) ? p.project_code.includes(dv.current().code) : p.project_code == dv.current().code));

dv.table(
  ["Title", "Citekey", "Author", "Year", "Zotero"],
  pages.sort(p => p.year, "desc").map(p => {
    const titleLink = dv.fileLink(p.file.path, false, p.title || p.file.name);
    const firstAuthor = p.authors && p.authors.length > 0 ? String(p.authors[0]).replace(/,.*$/, "") : "Unknown";
    const authorStr = p.authors && p.authors.length > 1 ? firstAuthor + " et al." : firstAuthor;
    const zoteroUrl = \`zotero://select/items/0_\${p.zotero_key}\`;
    const zoteroLink = \`[↗ Zotero](\${zoteroUrl})\`;
    return [titleLink, p.citekey || "", authorStr, p.year || "", zoteroLink];
  })
);
\`\`\`
`;

const projectPath = `${basePath}/_project.md`;
const existingProject = app.vault.getAbstractFileByPath(projectPath);
if (existingProject) {
    await app.vault.modify(existingProject, projectContent);
} else {
    await app.vault.create(projectPath, projectContent);
}

    await app.workspace.openLinkText(`${basePath}/_project`, "");
    await addNotification("Project Created", `Project ${code} - ${title} has been successfully created.`);
    new Notice(`✅ Project created: ${code} | Stickers ok:${stickerApplied} err:${stickerFailed} | New coauthors in DB:${addedNewPeople}`);
    success = true;
} catch (err) {
    errorObject = err;
    throw err;
} finally {
    if (!success) {
        let details = [];
        if (code) details.push(`Code: ${code}`);
        if (title) details.push(`Title: ${title}`);
        
        let notiTitle = "Project creation Cancelled";
        let msg = "";
        
        if (errorObject) {
            notiTitle = "Project creation Failed (Bug)";
            msg = `Project creation failed due to a system bug: ${errorObject.message || errorObject}.`;
            if (details.length > 0) {
                msg += ` (${details.join(" | ")})`;
            }
        } else {
            msg = details.length > 0 ? `Project creation was cancelled by the user (${details.join(" | ")}).` : "Project creation was cancelled by the user.";
        }
        await addNotification(notiTitle, msg);
    }
}

tR += "";
_%>
