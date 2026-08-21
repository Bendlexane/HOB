<p align="center">
  <img src=".obsidian/logo/hob-icon-full.svg" alt="HOB Logo" width="450" />
</p>

# HOB — Research Vault Toolkit

**BETA VERSION** — A free, open-source Obsidian vault template acting as Research Manadgment System (RMS) for running a complete scientific research workflow: projects, grants, lab notes, writing, summaries, literature, KPIs, and automation, powered by a local-first AI stack.

HOB started as one researcher's daily setup and is published here so other researchers can adopt it, break it, and improve it. It ships as a **ready-to-clone vault**, not a single plugin — most of what makes it useful (the scheduler, the Zotero pipeline, the Bayesian forecasting) runs outside Obsidian's plugin sandbox entirely.

---

## What's in the box

| Layer | What it does |
|---|---|
| **Dashboard** (`_HOME.md`) | A dataviewjs home view — greeting, clock, weather, calendar, an AI-powered search bar, and a "Vault Actions" quick-launch grid. |
| **Scheduler** (`_scripts/cron/`) | macOS `launchd`-based job runner — 9 daily automations, no cron, no extra permissions needed. |
| **Zotero pipeline** (`_scripts/kpi/`, `_scripts/automation/zotero_*`) | PDF/annotation ingestion, AI-assisted synthesis, auto-tagging, reading stats. |
| **Bayesian forecasting** (`_scripts/ml/`) | Predicts realistic project-phase durations from your own git history and draws a Mermaid Gantt "today" line. |
| **Ops** (`_scripts/ops/`) | Health checks, cron heartbeat monitoring, JSON-Schema frontmatter validation. |
| **Action framework** (`_scripts/actions/`) | Launcher-agnostic scripted actions behind the dashboard's quick-action buttons. |
| **Templates** (`_scripts/templates/`, `_templates/`) | 18 Templater templates: new project, new grant, protocol, lab note, peer review, conference/mission, and more. |
| **Theme** (`.obsidian/themes/HOB Glass/`) | A frosted-glass Obsidian theme. |
| **Sky Background** (`.obsidian/plugins/sky-background/`) | A small Obsidian plugin rendering a time-of-day sky behind the glass panels. |

It also provide built in connection to Zotero, iOS calendar, weather forecast and much more. 

## Need help?

Ask the HOB-AI what HOB can do for you and it will help you can get things done! 

## Plugins

The 7 plugins HOB's own code actually depends on ship **pre-built inside this repo** (`.obsidian/plugins/`) — Dataview, Templater, QuickAdd, Full Calendar, Sky Background, [llm-wiki](https://github.com/domleca/llm-wiki) (Ask-AI search — not in Obsidian's official registry, which is why it's bundled rather than linked), and [HOB's `home-tab` fork](https://github.com/Bendlexane/obsidian-home-tab) (folder search + Ask-AI Enter routing, a maintained fork of [olrenso/obsidian-home-tab](https://github.com/olrenso/obsidian-home-tab), used **instead of** the stock plugin, not alongside it). They activate the moment you turn on community plugins — nothing else to install for the dashboard to work.

Everything else in `.obsidian/community-plugins.json` (Zotero connector, PDF++, Git, and other supporting plugins) is optional — Obsidian will offer to install each one from its own browser, on your call.

## Setup

1. Clone this repo and open it as a vault: `File → Open vault → /path/to/HOB`
2. Obsidian will prompt about community plugins being present — turn them on (Settings → Community plugins). That's it for the plugins covered above; install any of the optional ones you also want.
3. Copy both env files and fill them in:
   ```bash
   cp .env.example .env                          # read by Templater/dataviewjs (AI_URL, CROSSREF_MAILTO, ...)
   cp _scripts/.env.example _scripts/.env         # read by the Python automations (VAULT_ROOT, ZOTERO_DB, ...)
   ```
4. Set up the Python side:
   ```bash
   cd _scripts
   python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   # optional, only if you use audio transcription:
   pip install -r requirements-transcription.txt
   python3 cron/setup_launchd.py
   python3 ops/health_check.py --no-write   # smoke test
   ```

**macOS only.** The scheduler is built on `launchd`; the Python scripts themselves are portable, but running them under cron/systemd on Linux is untested.

## Folder layout

Numbered top-level folders for stable ordering — see the short `README`/hub note in each for what belongs there: `00_STAGING` (inbox), `01_PROJECTS`, `02_GRANTS`, `03_KNOWLEDGE` (literature/concepts/protocols), `04_PEOPLE` (collaborators), `05_ADMIN`, `06_PLANNING` (KPIs), `07_INNOVATION`, `08_TEACHING`, `09_PEER_REVIEWS`, `99_ARCHIVE`. The automations assume this layout — if your own vault uses different names, you'll need to either adopt these or adjust the scripts yourself.

## License

MIT — see [LICENSE](LICENSE). This covers the vault structure, theme, plugin, and all `_scripts/` automation. It does **not** cover any content you put in your own vault once you start using it.

## Credits

- Theme and dashboard originally built around [Obsidian](https://obsidian.md/) — HOB is an independent toolkit that runs on top of the stock app, not a modified build of it.
- `home-tab` fork based on [olrenso/obsidian-home-tab](https://github.com/olrenso/obsidian-home-tab) (MIT) by Lorenzo.
- Ask-AI search powered by [llm-wiki](https://github.com/domleca/llm-wiki) (MIT) by Dominique Leca.
- Bundled, unmodified: [Dataview](https://github.com/blacksmithgu/obsidian-dataview), [Templater](https://github.com/SilentVoid13/Templater), [QuickAdd](https://github.com/chhoumann/quickadd), [Full Calendar](https://github.com/obsidian-community/obsidian-full-calendar) — each MIT-licensed, credit to their respective authors.
