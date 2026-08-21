/**
 * clean_tags_zotero_library.js
 * 
 * ⚠️ THIS SCRIPT RUNS INSIDE ZOTERO, NOT THE OBSIDIAN VAULT.
 * It must be inserted and configured as a script inside the Zotero "Actions and Tags" plugin.
 * 
 * This script cleans and formats paper tags automatically using GPTOSS-120B with
 * free API usage from Ollama, classifying papers in Zotero into standard categories.
 */


// ── CONFIG ──────────────────────────────────────────────────────────────────
const OLLAMA_URL = "https://api.ollama.com/api/generate";
const OLLAMA_MODEL = "gpt-oss:120b-cloud";
const OLLAMA_KEY = "PASTE_YOUR_OLLAMA_KEY_HERE"; // ⚠️ paste your key here before running — see OLLAMA_API_KEY in _scripts/.env
const TIMEOUT_MS = 30000;

// ⚠️ SYSTEM FRAGILITY WARNING:
// The CATEGORIES list is duplicated between this Zotero JS script and
// the Python KPI script `_scripts/kpi/zotero_stats.py`. If you modify categories
// here, you MUST also update them there to prevent pipeline/KPI collection breakage.
const CATEGORIES = new Set([
    "phylogenomics", "taxonomy", "morphometry", "ecology_biogeography",
    "genetics", "cytogenetics", "stats_ml", "methods_software",
    "philosophy", "informatics", "other"
]);
const ALLOWED_TYPES = new Set([
    "journalArticle", "preprint", "book", "bookSection", "conferencePaper",
    "thesis", "report", "manuscript", "document"
]);
// ────────────────────────────────────────────────────────────────────────────

function ollamaRequest(prompt) {
    return new Promise((resolve, reject) => {
        if (!OLLAMA_KEY || OLLAMA_KEY === "PASTE_YOUR_OLLAMA_KEY_HERE") {
            reject(new Error("OLLAMA_KEY not set — edit the CONFIG block at the top of this script."));
            return;
        }
        const xhr = new XMLHttpRequest();
        xhr.open("POST", OLLAMA_URL, true);
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.setRequestHeader("Authorization", "Bearer " + OLLAMA_KEY);
        xhr.timeout = TIMEOUT_MS;
        xhr.ontimeout = () => reject(new Error("timeout"));
        xhr.onerror = () => reject(new Error("network error"));
        xhr.onload = () => xhr.status === 200 ? resolve(xhr.responseText) : reject(new Error(`HTTP ${xhr.status}`));
        xhr.send(JSON.stringify({ model: OLLAMA_MODEL, prompt, stream: false, options: { temperature: 0.1 } }));
    });
}

async function classify(title, abstract, idx, total) {
    Zotero.log(`[KPI batch] [${idx}/${total}] → Ollama request: "${title.slice(0, 60)}"`);
    const prompt = `Classify the following scientific paper into EXACTLY ONE category.
Respond ONLY with: {"category": "...", "reason": "..."}

RULES when categories overlap:
- Phylogenetic tree or network is the main output → phylogenomics
- Molecular data used to resolve species identity or nomenclature → taxonomy
- Morphometric analysis (GMM, geometric) without formal nomenclatural acts → morphometry
- Morphometrics as one tool among several in a formal species revision → taxonomy
- Molecular markers for population structure without a phylogenetic tree → genetics
- Named software tool, Shiny app, or pipeline delivered → methods_software
- Floristic surveys, regional checklists, new territory records → taxonomy
- CS/software/AI without biological application → informatics
- Paper unrelated to plant evolutionary biology or CS → other
- Allometry referring to shape/size variation among specimens or populations → morphometry (NOT ecology_biogeography)
- Ecological scaling laws (body size vs metabolic rate, biomass, geographic range) → ecology_biogeography

CATEGORIES:
- phylogenomics: molecular trees, phylogeography, diversification rates, ancestral states, reticulate evolution (when tree is the primary output)
- taxonomy: species delimitation, nomenclatural acts, revisionary work, integrative taxonomy with formal outcomes, floristic surveys and checklists
- morphometry: quantitative shape/size analysis (geometric morphometrics, GMM, allometry) even when used to evaluate species boundaries without nomenclatural acts
- ecology_biogeography: SDMs, niche modelling, phytosociology, vegetation classification, community ecology, conservation ecology
- genetics: population structure, AFLP/RADseq/SSR/SNPs/cpDNA, gene flow, hybridization, admixture, epigenetic variation (no phylogenetic tree as main output)
- cytogenetics: genome size, flow cytometry, karyology, polyploidy, chromosome counts, C-values
- stats_ml: statistical or computational framework applicable across study systems (Bayesian methods, ML algorithms, R/Python packages, probabilistic models)
- methods_software: named software tools, databases, pipelines, lab protocols (e.g. HybPiper, BPP, Shiny apps, chromosome databases, DNA extraction protocols)
- philosophy: history of systematics or biometry, species concept theory, ontology of biological taxa, scientific methodology critique
- informatics: computer science, coding, software engineering, AI/ML systems, agent systems — without direct biological application
- other: medicine, veterinary, energy systems, human ecology, social sciences
- morphometry: quantitative shape/size analysis among specimens/populations/taxa
  (geometric morphometrics, GMM, traditional morphometrics, organismal allometry)

Title: ${title}
Abstract: ${abstract}`;

    try {
        const resp = await ollamaRequest(prompt);
        const raw = (JSON.parse(resp).response || "").trim()
            .replace(/^```[^\n]*\n?/, "").replace(/```$/, "").trim();
        Zotero.log(`[KPI batch] [${idx}/${total}] ← raw: ${raw.slice(0, 100)}`);
        let cat = null, reason = "";
        try {
            const parsed = JSON.parse(raw);
            cat = parsed.category;
            reason = parsed.reason || "";
        } catch {
            const m = raw.match(/"category"\s*:\s*"([^"]+)"/);
            cat = m?.[1] ?? null;
            Zotero.log(`[KPI batch] [${idx}/${total}] fallback regex parse → ${cat}`);
        }
        const result = CATEGORIES.has(cat) ? cat : "other";
        Zotero.log(`[KPI batch] [${idx}/${total}] ✓ ${result} — ${reason.slice(0, 80)}`);
        return result;
    } catch (e) {
        Zotero.logError(`[KPI batch] [${idx}/${total}] Ollama error: ${e.message}`);
        return "other";
    }
}

// ── MAIN ────────────────────────────────────────────────────────────────────
Zotero.log("[KPI batch] ══ START ══ loading items from user library…");
const allItems = await Zotero.Items.getAll(Zotero.Libraries.userLibraryID);
Zotero.log(`[KPI batch] total items in library: ${allItems.length}`);

const papers = allItems.filter(it =>
    !it.isNote() && !it.isAttachment() && !it.isAnnotation() &&
    ALLOWED_TYPES.has(Zotero.ItemTypes.getName(it.itemTypeID))
);
Zotero.log(`[KPI batch] eligible papers: ${papers.length}`);

let nCleaned = 0, nClassified = 0, nSkipped = 0, nErrors = 0;

for (let i = 0; i < papers.length; i++) {
    const it = papers[i];
    const title = (it.getField("title") || "").trim();
    const tags = it.getTags().map(t => t.tag);

    // Strip non-category tags
    const toStrip = tags.filter(t => !CATEGORIES.has(t));
    for (const t of toStrip) it.removeTag(t);
    if (toStrip.length) Zotero.log(`[KPI batch] [${i + 1}/${papers.length}] stripped ${toStrip.length} keyword(s) from "${title.slice(0, 50)}"`);

    const existingCat = tags.find(t => CATEGORIES.has(t));
    if (existingCat) {
        Zotero.log(`[KPI batch] [${i + 1}/${papers.length}] SKIP (already: ${existingCat}) "${title.slice(0, 50)}"`);
        nSkipped++;
        if (toStrip.length) await it.saveTx();
        nCleaned++;
        continue;
    }

    const abstract = (it.getField("abstractNote") || "").trim().slice(0, 2000);
    if (!title && !abstract) {
        Zotero.log(`[KPI batch] [${i + 1}/${papers.length}] SKIP (no title/abstract)`);
        nCleaned++;
        continue;
    }

    const cat = await classify(title, abstract, i + 1, papers.length);
    it.addTag(cat);
    nClassified++;

    await it.saveTx();
    nCleaned++;

    // Progress summary every 20 papers
    if ((i + 1) % 20 === 0) {
        Zotero.log(`[KPI batch] ── progress: ${i + 1}/${papers.length} | classified: ${nClassified} | skipped: ${nSkipped} | errors: ${nErrors} ──`);
    }
}

const summary = `✓ ${nCleaned} paper processati — ${nClassified} classificati, ${nSkipped} già ok, ${nErrors} errori.`;
Zotero.log(`[KPI batch] ══ DONE ══ ${summary}`);
return summary;