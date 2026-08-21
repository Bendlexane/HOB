/**
 * Zotero Actions & Tags — customScript
 * Event: createItem
 * Classifies new papers into macro-categories via Ollama gpt-oss:120b-cloud.
 * Works across ALL Zotero libraries (user + group).
 *
 * HOW TO INSTALL:
 * 1. Zotero → Tools → Add-ons → Actions & Tags → Preferences
 * 2. Click "+" → set:
 *      Event:       createItem
 *      Operation:   customScript
 *      Enabled:     ✓
 *      Menu Label:  (leave empty)
 *      Shortcut:    (leave empty)
 *      Data:        paste this entire script
 * 3. Save
 *
 * REQUIREMENTS:
 * - Ollama running on localhost:11434 with gpt-oss:120b-cloud
 *   (or change the model name below)
 */

const ALLOWED_TYPES = new Set([
  "journalArticle",
  "preprint",
  "book",
  "bookSection",
  "conferencePaper",
  "thesis",
  "report",
  "manuscript",
  "document",
]);

const CATEGORIES = [
  "phylogenomics",
  "taxonomy",
  "morphometry",
  "ecology_biogeography",
  "genetics",
  "cytogenetics",
  "stats_ml",
  "methods_software",
  "philosophy",
  "informatics",
  "other",
];

const OLLAMA_URL = "http://localhost:11434/api/generate";
const OLLAMA_MODEL = "gpt-oss:120b-cloud";
const TIMEOUT_MS = 60000;

function ollamaRequest(prompt) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", OLLAMA_URL, true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.timeout = TIMEOUT_MS;
    xhr.ontimeout = () => reject(new Error("Ollama timeout"));
    xhr.onerror = () => reject(new Error("Ollama network error"));
    xhr.onload = () => {
      if (xhr.status === 200) resolve(xhr.responseText);
      else reject(new Error(`HTTP ${xhr.status}`));
    };
    xhr.send(
      JSON.stringify({
        model: OLLAMA_MODEL,
        prompt: prompt,
        stream: false,
        options: { temperature: 0.1 },
      })
    );
  });
}

(async () => {
  Zotero.log('[KPI] Script triggered — item: ' + (item ? item.getField('title') : 'null'));
  if (!item) return;
  if (item.isNote() || item.isAttachment() || item.isAnnotation()) return;

  const itemType = Zotero.ItemTypes.getName(item.itemTypeID);
  if (!ALLOWED_TYPES.has(itemType)) return;

  // Strip all imported keyword tags — keep only category tags
  const existingTags = item.getTags().map((t) => t.tag);
  for (const t of existingTags) {
    if (!CATEGORIES.includes(t)) item.removeTag(t);
  }

  if (existingTags.some((t) => CATEGORIES.includes(t))) {
    await item.saveTx();
    return;
  }

  const title = (item.getField("title") || "").trim();
  const abstract = (item.getField("abstractNote") || "").trim().slice(0, 2000);
  if (!title && !abstract) return;

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
- Allometry comparing shape/size among specimens, populations, or taxa → morphometry
- Allometry as ecological scaling law (body size vs metabolic rate, biomass) → ecology_biogeography
- Paper unrelated to plant evolutionary biology → other

CATEGORIES:
- phylogenomics: molecular trees, phylogeography, diversification rates, ancestral states, reticulate evolution (when tree is the primary output)
- taxonomy: species delimitation, nomenclatural acts, revisionary work, integrative taxonomy with formal outcomes, floristic surveys and checklists
- morphometry: quantitative shape/size analysis among specimens/populations/taxa (geometric morphometrics, GMM, traditional morphometrics, organismal allometry) even when used to evaluate species boundaries without nomenclatural acts
- ecology_biogeography: SDMs, niche modelling, phytosociology, vegetation classification, community ecology, conservation ecology
- genetics: population structure, AFLP/RADseq/SSR/SNPs/cpDNA, gene flow, hybridization, admixture, epigenetic variation (no phylogenetic tree as main output)
- cytogenetics: genome size, flow cytometry, karyology, polyploidy, chromosome counts, C-values
- stats_ml: statistical or computational framework applicable across study systems (Bayesian methods, ML algorithms, R/Python packages, probabilistic models)
- methods_software: named software tools, databases, pipelines, lab protocols (e.g. HybPiper, BPP, Shiny apps, chromosome databases, DNA extraction protocols)
- philosophy: history of systematics or biometry, species concept theory, ontology of biological taxa, scientific methodology critique
- informatics: computer science, coding, software engineering, AI/ML systems, agent systems — without direct biological application
- other: medicine, veterinary, energy systems, human ecology, social sciences

Title: ${title}
Abstract: ${abstract}`;

  let responseText;
  try {
    responseText = await ollamaRequest(prompt);
  } catch (e) {
    Zotero.logError(`[KPI] Ollama: ${e.message}`);
    return;
  }

  let category = null;
  try {
    const data = JSON.parse(responseText);
    const raw = (data.response || "").trim();
    const parsed = JSON.parse(raw);
    category = parsed.category;
  } catch {
    const raw = (JSON.parse(responseText).response || "").trim();
    const m = raw.match(/"category"\s*:\s*"([^"]+)"/);
    category = m ? m[1] : null;
  }

  if (!category || !CATEGORIES.includes(category)) return;

  try {
    item.addTag(category);
    await item.saveTx();
    Zotero.log(`[KPI] Tagged "${title.slice(0, 60)}..." as ${category}`);
  } catch (e) {
    Zotero.logError(`[KPI] Save failed: ${e.message}`);
  }
})();
