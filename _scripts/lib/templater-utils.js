// ============================================================================
//  templater-utils.js — shared helpers for Templater templates
// ----------------------------------------------------------------------------
//  Single source of truth for logic that used to be copy-pasted across many
//  templates (make.md folder notes, the date-picker modal, the Ollama call +
//  JSON extraction, the conference session/table builders, the people DB).
//
//  Usage (cache-busted require, so edits here take effect without restarting
//  Obsidian — just re-run the template):
//
//    const _lp = `${app.vault.adapter.basePath}/_scripts/lib/templater-utils.js`;
//    try { delete require.cache[_lp]; } catch (e) {}
//    const U = require(_lp);
//
//  Then call e.g. U.getStickerNoteTargets(path), await U.pickDate("Start date").
//
//  Globals used: `app`, `moment`, `document`, `fetch` are all provided by the
//  Obsidian renderer and resolve here via `window.*`. No `tp` is needed — pass
//  any tp-derived value (or use U.today()) as an argument instead.
// ============================================================================

const app = window.app;
const moment = window.moment;

// ─── path / string helpers ──────────────────────────────────────────────────
function basename(path) {
  const parts = path.split("/").filter(Boolean);
  return parts[parts.length - 1] || path;
}

function ensureMd(name) {
  return name.toLowerCase().endsWith(".md") ? name : `${name}.md`;
}

function normalizeSpaces(s) {
  return (s || "").replace(/\s+/g, " ").trim();
}

function titleCase(s) {
  return (s || "")
    .split(" ")
    .map(p => (p ? p.charAt(0).toUpperCase() + p.slice(1) : p))
    .join(" ");
}

function generateSlug(str) {
  return normalizeSpaces(str || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");
}

// Today as YYYY-MM-DD (equivalent to tp.date.now("YYYY-MM-DD")).
function today() {
  return moment().format("YYYY-MM-DD");
}

// ─── make.md folder-note helpers ────────────────────────────────────────────
// Resolve where the folder note for `folderPath` lives, honoring make.md's
// folderNoteName / folderNoteInsideFolder settings.
function getStickerNoteTargets(folderPath) {
  const targets = new Set();
  const makeMd = app.plugins?.plugins?.["make-md"]?.superstate?.settings;
  const folderNoteNameSetting = (makeMd?.folderNoteName || "").trim();
  const noteFileName = ensureMd(folderNoteNameSetting || basename(folderPath));

  if (makeMd?.folderNoteInsideFolder === false) {
    const parent = folderPath.split("/").slice(0, -1).join("/");
    targets.add(`${parent}/${noteFileName}`);
  } else {
    targets.add(`${folderPath}/${noteFileName}`);
  }
  return Array.from(targets);
}

async function refreshMakeMdPaths(folderPaths) {
  const makeMd = app.plugins?.plugins?.["make-md"]?.superstate;
  if (!makeMd) return;
  for (const p of folderPaths) {
    try { await makeMd.reloadPath?.(p, true); } catch (e) {}
    try { await makeMd.reloadContextByPath?.(p, { force: true, calculate: true }); } catch (e) {}
  }
}

// ─── date-picker modal ──────────────────────────────────────────────────────
// Returns the picked YYYY-MM-DD string, or "" if cancelled (Enter = Set).
function pickDate(label, defaultDate) {
  return new Promise(resolve => {
    const value = defaultDate || moment().format("YYYY-MM-DD");
    const container = document.createElement("div");
    container.style.cssText = "position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.4);z-index:10000;display:flex;align-items:center;justify-content:center;";
    const dialog = document.createElement("div");
    dialog.style.cssText = "background:var(--background-primary);border-radius:8px;padding:24px;box-shadow:0 4px 24px rgba(0,0,0,0.3);min-width:280px;";
    dialog.innerHTML = `
      <h3 style="margin:0 0 16px;font-size:1.1em;">${label}</h3>
      <input type="date" id="md-date" value="${value}"
             style="width:100%;padding:8px;font-size:1.1em;margin-bottom:16px;background:var(--background-secondary);color:var(--text-normal);border:1px solid var(--background-modifier-border);border-radius:4px;box-sizing:border-box;">
      <div style="display:flex;gap:8px;justify-content:flex-end;">
        <button id="md-cancel" style="padding:6px 16px;border-radius:4px;cursor:pointer;background:var(--background-secondary);color:var(--text-normal);border:1px solid var(--background-modifier-border);">Cancel</button>
        <button id="md-set" style="padding:6px 16px;background:var(--interactive-accent);color:var(--text-on-accent);border:none;border-radius:4px;cursor:pointer;">Set</button>
      </div>
    `;
    container.appendChild(dialog);
    document.body.appendChild(container);
    const inp = dialog.querySelector("#md-date");
    const close = val => { document.body.removeChild(container); resolve(val); };
    dialog.querySelector("#md-set").onclick = () => close(inp.value ? inp.value : "");
    dialog.querySelector("#md-cancel").onclick = () => close("");
    inp.onkeydown = e => { if (e.key === "Enter") dialog.querySelector("#md-set").click(); };
    inp.focus();
  });
}

// ─── .env loader (KEY=value lines, '#' comments) ─────────────────────────────
async function loadEnv() {
  try {
    const f = app.vault.getAbstractFileByPath(".env");
    if (!f) return {};
    const c = await app.vault.read(f);
    const e = {};
    for (const line of c.split("\n")) {
      const t = line.trim();
      if (t && !t.startsWith("#")) {
        const eq = t.indexOf("=");
        if (eq > 0) e[t.slice(0, eq).trim()] = t.slice(eq + 1).trim();
      }
    }
    return e;
  } catch {
    return {};
  }
}

// ─── YAML file loader ───────────────────────────────────────────────────────
// Minimal, dependency-free parser for the restricted YAML subset used by
// _scripts/ops/grant_profiles/*.yaml (and similar config files): full-line
// '#' comments, flat `key: scalar` pairs, nested blocks, and lists of either
// scalars or flat objects, using consistent 2-space indentation. Not a
// general YAML parser — no external YAML library is available in this
// environment (Node's require has no js-yaml, and Obsidian's own
// parseYaml is not reliably reachable from a Templater user script).
function parseSimpleYaml(text) {
  const lines = [];
  for (const raw of text.split("\n")) {
    const stripped = raw.replace(/^(\s*)#.*/, "$1");
    if (!stripped.trim()) continue;
    lines.push({ indent: stripped.match(/^ */)[0].length, text: stripped.trim() });
  }

  function parseScalar(s) {
    if (s === "" || s === "null" || s === "~") return null;
    if (s === "true") return true;
    if (s === "false") return false;
    if (/^-?\d+(\.\d+)?$/.test(s)) return Number(s);
    const m = s.match(/^"(.*)"$/);
    return m ? m[1].replace(/\\"/g, '"') : s;
  }

  const KEY_RE = /^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$/;
  let i = 0;

  function parseBlock(indent) {
    const obj = {};
    while (i < lines.length && lines[i].indent === indent) {
      const m = lines[i].text.match(KEY_RE);
      if (!m) break; // not a key: line at this indent — let the caller handle it
      const [, key, rest] = m;
      i++;
      if (rest !== "") {
        obj[key] = parseScalar(rest);
      } else if (i < lines.length && lines[i].indent > indent && lines[i].text.startsWith("- ")) {
        obj[key] = parseList(lines[i].indent);
      } else if (i < lines.length && lines[i].indent > indent) {
        obj[key] = parseBlock(lines[i].indent);
      } else {
        obj[key] = null;
      }
    }
    return obj;
  }

  function parseList(indent) {
    const arr = [];
    while (i < lines.length && lines[i].indent === indent && lines[i].text.startsWith("- ")) {
      const itemText = lines[i].text.slice(2).trim();
      const km = !itemText.startsWith('"') && itemText.match(KEY_RE);
      if (!km) {
        arr.push(parseScalar(itemText));
        i++;
        continue;
      }
      const item = { [km[1]]: parseScalar(km[2]) };
      i++;
      const itemIndent = indent + 2;
      Object.assign(item, parseBlock(itemIndent));
      arr.push(item);
    }
    return arr;
  }

  return parseBlock(0);
}

// Reads and parses a vault-relative YAML file (restricted subset — see
// parseSimpleYaml). Returns null if the file is missing or fails to parse.
async function readYaml(path) {
  try {
    const f = app.vault.getAbstractFileByPath(path);
    if (!f) return null;
    const text = await app.vault.read(f);
    return parseSimpleYaml(text);
  } catch (e) {
    console.error("readYaml failed for", path, e);
    return null;
  }
}

// ─── Ollama / local LLM helpers ─────────────────────────────────────────────
// Fire-and-forget generate call. Returns the response string, or "" on any
// failure (callers decide how to surface an empty result).
async function aiFetch({ url, model, prompt, system, temperature = 0.1 } = {}) {
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, prompt, system, stream: false, options: { temperature } }),
    });
    return (await r.json()).response || "";
  } catch {
    return "";
  }
}

// Pull the first {...} JSON object out of a raw LLM response. Returns `fallback`
// (default null) if nothing parseable is found.
function extractJson(raw, fallback = null) {
  try {
    const m = (raw || "").match(/\{[\s\S]*\}/);
    if (m) return JSON.parse(m[0]);
  } catch {}
  return fallback;
}

// ─── conference programme → daily-note builders ─────────────────────────────
const CB = String.fromCharCode(96, 96, 96); // ```  (triple backtick fence)
const BT = String.fromCharCode(96);          // `   (single backtick)

// Prompt that asks the LLM to extract one conference day as structured JSON.
function dayExtractionPrompt(dayNum, dateStr, programme) {
  return (
    `Extract from the conference programme only content for day ${dayNum} (${dateStr}).\n` +
    `Output ONLY valid JSON, no other text:\n` +
    `{"sessions":[{"time_start":"HH:MM","time_end":"HH:MM","title":"...","venue":"...","speakers":["..."],"type":"keynote|session|workshop|poster|break","track":"... (optional parent symposium name)"}],"main_themes":["..."]}\n` +
    `For each session extract the exact start and end time (e.g. "09:00–17:00" → time_start "09:00", time_end "17:00").\n` +
    `Rules: do not invent; use null for unknown; if no content for this day output {"sessions":[],"main_themes":[]}.\n` +
    `PROGRAMME:\n${(programme || "").slice(0, 30000)}`
  );
}

// Mermaid gantt init block used by every daily note (green theme).
const ganttInitBlock =
`%%{
  init: {
    'theme': 'base',
    'gantt': { 'fontSize': 28, 'barHeight': 70, 'barGap': 12, 'topPadding': 40, 'leftPadding': 120 },
    'themeVariables': {
      'primaryColor': '#4CAF50',
      'primaryBorderColor': '#2E7D32',
      'primaryTextColor': '#000000',
      'lineColor': '#616161',
      'secondaryColor': '#E8F5E9',
      'tertiaryColor': '#C8E6C9',
      'textColor': '#000000',
      'fontSize': '28px'
    }
  }
}%%`;

// Gantt task rows for the day (defaults to a single 8h placeholder bar).
function sessionGanttRows(active) {
  if (!active || !active.length) return "    Sessions : 09:00, 8h";
  const rows = active
    .filter(s => s.time_start)
    .map(s => {
      const title = (s.title || "Session").replace(/:/g, "").slice(0, 50);
      return `    ${title} : ${s.time_start}, ${s.time_end || "1h"}`;
    })
    .join("\n");
  return rows || "    Sessions : 09:00, 8h";
}

// Markdown table of all sessions; single column when ≤1 venue, otherwise a
// time × venue grid.
function buildSessionTable(sessions) {
  if (!sessions.length) return "_No sessions._";
  const venues = [...new Set(sessions.filter(s => s.venue).map(s => s.venue))].sort();
  const sorted = [...sessions].sort((a, b) => (a.time_start || "").localeCompare(b.time_start || ""));

  if (venues.length <= 1) {
    let t = "| Time | Activity | Speakers |\n|------|----------|----------|\n";
    for (const s of sorted) {
      const sp = (s.speakers || []).filter(Boolean).join(", ") || "—";
      t += `| ${s.time_start || "—"}–${s.time_end || "—"} | ${s.title || "—"}${s.venue ? `<br>_${s.venue}_` : ""} | ${sp} |\n`;
    }
    return t;
  }

  const trs = [];
  const seen = new Set();
  for (const s of sessions) {
    const k = `${s.time_start}-${s.time_end}`;
    if (!seen.has(k) && s.time_start && s.time_end) { seen.add(k); trs.push({ start: s.time_start, end: s.time_end }); }
  }
  trs.sort((a, b) => a.start.localeCompare(b.start));

  let t = `| Time | ${venues.join(" | ")} |\n`;
  t += `|${["------", ...venues.map(() => "----------")].join("|")}|\n`;
  for (const tr of trs) {
    const rs = sessions.filter(s => s.time_start === tr.start && s.time_end === tr.end);
    const cells = [`${tr.start}–${tr.end}`];
    for (const v of venues) {
      const s = rs.find(x => x.venue === v);
      cells.push(s ? `**${s.title}**${(s.speakers || []).filter(Boolean).length ? `<br>_${s.speakers.filter(Boolean).join(", ")}_` : ""}` : "_—_");
    }
    t += `| ${cells.join(" | ")} |\n`;
  }
  return t;
}

// A single talk block: heading + per-talk record button + notes scaffold.
function buildTalk(s, dateStr, idx) {
  const btnId = `rec-toggle-${dateStr}-${idx}`;
  const sp = (s.speakers || []).filter(Boolean).join(", ");
  const ven = s.venue ? ` · **Venue:** ${s.venue}` : "";
  const spe = sp ? ` · **Speakers:** ${sp}` : "";
  return (
    `#### ${s.title || "Session"}\n\n` +
    `${CB}button\n` +
    `name 🎙 Record\n` +
    `type command\n` +
    `action Templater: Insert mplates/record-session-toggle\n` +
    `id ${btnId}\n` +
    `${CB}\n` +
    `^${btnId}\n` +
    `**Time:** ${s.time_start || "—"}–${s.time_end || "—"}${ven}${spe}\n\n` +
    `##### Handwritten Notes\n\n` +
    `##### Questions / Follow-Up\n- [ ]\n`
  );
}

// All talk blocks for the day, grouped by track then track-less.
function buildTalksSection(sessions, dateStr) {
  const active = sessions.filter(s => s.type !== "break");
  if (!active.length) return "\n_No sessions to take notes on._\n";

  const withTrack = active.filter(s => s.track);
  const withoutTrack = active.filter(s => !s.track);
  const tracks = [...new Set(withTrack.map(s => s.track))];
  let out = "\n";
  let idx = 0;

  for (const track of tracks) {
    out += `### ${track}\n\n`;
    for (const s of withTrack.filter(x => x.track === track)) out += buildTalk(s, dateStr, idx++);
  }
  for (const s of withoutTrack) out += buildTalk(s, dateStr, idx++);
  return out;
}

// Build the "# Schedule Overview" + "# Session Breakdown" sections for one day
// from a (validated) sessions array. Returns { newSchedule, newBreakdown }.
function buildDaySections(dayNum, dateStr, sessions) {
  const safe = Array.isArray(sessions) ? sessions : [];
  const active = safe.filter(s => s.type !== "break");
  const all = [...active, ...safe.filter(s => s.type === "break")];
  all.sort((a, b) => (a.time_start || "").localeCompare(b.time_start || ""));

  const newSchedule =
    `# Schedule Overview\n\n${CB}mermaid\n${ganttInitBlock}\ngantt\n    title Day ${dayNum} Schedule\n    dateFormat HH:mm\n    axisFormat %H:%M\n\n    section Sessions\n${sessionGanttRows(active)}\n${CB}`;

  const newBreakdown = `# Session Breakdown\n\n${buildSessionTable(all)}\n\n## Talks${buildTalksSection(safe, dateStr)}`;
  return { newSchedule, newBreakdown };
}

// ─── people DB ──────────────────────────────────────────────────────────────
const PEOPLE_DB_PATH = "04_PEOPLE/collaborators/_people-db.json";

async function ensurePeopleDb() {
  const folderPath = "04_PEOPLE/collaborators";
  const folder = app.vault.getAbstractFileByPath(folderPath);
  if (!folder) {
    try { await app.vault.createFolder(folderPath); } catch (e) {}
  }
  let file = app.vault.getAbstractFileByPath(PEOPLE_DB_PATH);
  if (!file) {
    const initial = { version: 2, updated: today(), people: [] };
    await app.vault.create(PEOPLE_DB_PATH, JSON.stringify(initial, null, 2) + "\n");
    file = app.vault.getAbstractFileByPath(PEOPLE_DB_PATH);
  }
  return file;
}

// Returns { file, data }, repairing the file if it is corrupt.
async function readPeopleDb() {
  const file = await ensurePeopleDb();
  const raw = await app.vault.read(file);
  try {
    const parsed = JSON.parse(raw);
    if (!parsed.people || !Array.isArray(parsed.people)) parsed.people = [];
    return { file, data: parsed };
  } catch (e) {
    const fallback = { version: 2, updated: today(), people: [] };
    await app.vault.modify(file, JSON.stringify(fallback, null, 2) + "\n");
    return { file, data: fallback };
  }
}

async function savePeopleDb(file, data) {
  data.updated = today();
  data.people = (data.people || []).sort((a, b) =>
    (a.display_name || "").localeCompare(b.display_name || "", "en", { sensitivity: "base" })
  );
  await app.vault.modify(file, JSON.stringify(data, null, 2) + "\n");
}

module.exports = {
  // path / string
  basename, ensureMd, normalizeSpaces, titleCase, generateSlug, today,
  // make.md
  getStickerNoteTargets, refreshMakeMdPaths,
  // ui / io
  pickDate, loadEnv, readYaml,
  // llm
  aiFetch, extractJson, dayExtractionPrompt,
  // conference builders
  CB, BT, ganttInitBlock, sessionGanttRows, buildSessionTable, buildTalk, buildTalksSection, buildDaySections,
  // people db
  PEOPLE_DB_PATH, ensurePeopleDb, readPeopleDb, savePeopleDb,
};
