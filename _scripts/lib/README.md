# Library Config Registry (`_scripts/lib/`)

This directory houses configuration files and static registries used as metadata configurations across the Obsidian Vault dashboard and templates.

> [!IMPORTANT]
> **LLM INSTRUCTION RULE:** Any AI agent/LLM adding, modifying, or removing action templates or launcher workflows in `_templates/` or `_scripts/templates/` **MUST** update `actions-registry.json` and keep this `README.md` in sync.

---

## Files

### 1. `actions-registry.json`
- **Purpose**: The single source of truth for vault-wide quick actions. 
- **Consumed by**:
  1. **Dashboard Launcher**: The quick actions grid rendered in the main dashboard ([`_HOME.md`](_HOME.md)).
  2. **Templater Suggester**: The multi-step launcher workspace command picker ([`_templates/actions.md`](_templates/actions.md)).
- **Editing Guidelines**: If you add a new template script in `_scripts/templates/`, you must declare it here under its corresponding category block for it to appear in the launchers.

### 2. `templater-utils.js`
- **Purpose**: Single source of truth for the JavaScript helpers that the Templater templates in `_scripts/templates/` used to copy-paste. Centralizing them removes a whole class of bugs that came from copies drifting out of sync (e.g. the `ex.sessions` crash guard that existed in some copies but not others).
- **Consumed by**: `new-project`, `mission`, `fieldwork`, `peer-review`, `new-peer-round`, `people-db`, `regenerate-daily-note`, `regenerate-all-daily-notes`.

#### How to use it from a template
Paste this at the top of the `<%* … %>` block. The cache-bust (`delete require.cache`) makes edits to the lib take effect on the **next template run** — no Obsidian restart needed:

```js
const _lp = `${app.vault.adapter.basePath}/_scripts/lib/templater-utils.js`;
try { delete require.cache[_lp]; } catch (e) {}
const U = require(_lp);
// then: await U.pickDate("Start date"), U.getStickerNoteTargets(path), U.aiFetch({...}), …
```

In a large legacy template you can keep every existing call-site untouched by **aliasing** instead of rewriting (this is what `new-project.md` does):

```js
const normalizeSpaces = U.normalizeSpaces;
const getStickerNoteTargets = U.getStickerNoteTargets;
// delete the old local function definitions — the bare calls now resolve to the aliases
```

#### Exported API
| Group | Functions |
|---|---|
| Path / string | `basename`, `ensureMd`, `normalizeSpaces`, `titleCase`, `generateSlug`, `today()` |
| make.md folder notes | `getStickerNoteTargets(folderPath)`, `refreshMakeMdPaths(paths)` |
| UI / IO | `pickDate(label, default?)` (date-picker modal, returns `YYYY-MM-DD` or `""`), `loadEnv()` |
| Local LLM (Ollama) | `aiFetch({url, model, prompt, system?, temperature?})` (silent, returns `""` on failure), `extractJson(raw, fallback?)`, `dayExtractionPrompt(dayNum, dateStr, programme)` |
| Conference builders | `CB`, `BT`, `ganttInitBlock`, `sessionGanttRows(active)`, `buildSessionTable(sessions)`, `buildTalk(s, dateStr, idx)`, `buildTalksSection(sessions, dateStr)`, `buildDaySections(dayNum, dateStr, sessions)` |
| People DB | `PEOPLE_DB_PATH`, `ensurePeopleDb()`, `readPeopleDb()` → `{file, data}`, `savePeopleDb(file, data)` |

#### Conventions & constraints
- **CommonJS module**, no `tp`. It relies only on Obsidian renderer globals (`app`, `moment`, `document`, `fetch`); anything `tp`-derived must be passed in as an argument (or use `U.today()` instead of `tp.date.now`).
- **No-create reader**: `readPeopleDb()` *creates* the DB file if missing. Read-only views (`view-person.md`, `new-latex-abstract.md`) deliberately keep their own lightweight reader that returns `[]` without side effects — do not migrate them to `readPeopleDb()`.
- **`Notice` conventions** in templates that call this lib: `✅` success, `❌` errors and cancelled `return`s, `⏳` long/loading operations.
- **English only** in all template/lib strings and comments; no real third-party names in examples (use placeholders like `Smith, J.`).

> [!IMPORTANT]
> When you add a helper that is (or will be) used by more than one template, put it **here** rather than inlining a copy. That is the whole point of this file.
