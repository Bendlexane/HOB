<p align="center">
  <img src=".obsidian/logo/hob-icon-full.svg" alt="HOB Logo" width="450" />
</p>

# HOB — Research Vault Toolkit

**BETA VERSION** — A free, open-source Obsidian vault template acting as a Research Management System (RMS) for running a complete scientific research workflow: projects, grants, lab notes, writing, summaries, literature, KPIs, and automation, with an AI layer you point at the model of your choice.

> **HOB is not local-only out of the box.** It ships configured for `gpt-oss:120b-cloud`, a model that runs on Ollama's servers, and the AI layer is restricted to `03_KNOWLEDGE/` — your literature, concepts, methods and protocols. Projects, grants, people, admin and peer reviews are never indexed. Switching to a fully local model is one setting; see [What leaves your machine](#what-leaves-your-machine).

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

The 8 plugins HOB's own code actually depends on ship **pre-built inside this repo** (`.obsidian/plugins/`) — Dataview, Templater, QuickAdd, Full Calendar, Sky Background, [Make.md](https://github.com/Make-md/makemd) (folder notes, stickers and the Spaces navigator), [HOB's `llm-wiki` fork](https://github.com/Bendlexane/llm-wiki) (Ask-AI search, restricted to the knowledge layer so confidential material never enters the index; a maintained fork of [domleca/llm-wiki](https://github.com/domleca/llm-wiki), not in Obsidian's official registry, which is why it's bundled rather than linked), and [HOB's `home-tab` fork](https://github.com/Bendlexane/obsidian-home-tab) (folder search + Ask-AI Enter routing, a maintained fork of [olrenso/obsidian-home-tab](https://github.com/olrenso/obsidian-home-tab), used **instead of** the stock plugin, not alongside it). They activate the moment you turn on community plugins — nothing else to install for the dashboard to work.

`.obsidian/community-plugins.json` lists exactly those eight and nothing else, so a fresh clone starts clean. Anything else you want (Zotero connector, PDF++, Git, and so on) installs the normal way from Obsidian's own plugin browser.

## What leaves your machine

A research vault holds unpublished work, so it is worth being exact about which
parts of HOB talk to the outside world. Everything below is off unless the row
says otherwise, and nothing is telemetry — HOB collects nothing about you.

| What | Where it goes | When |
|---|---|---|
| **Notes in `03_KNOWLEDGE/`** | Ollama (**hosted by default**) | Ask-AI search, the AI helper card, and a nightly re-index at 02:00 |
| Your Ask-AI questions | Ollama (**hosted by default**) | Each time you ask |
| Paper titles and abstracts | Ollama (**hosted by default**) | Zotero tagging and annotation synthesis |
| Recorded audio | Stays local — Whisper runs on your machine | Session transcription |
| Transcript text | Ollama (**hosted by default**) | Cleanup pass after transcription |
| Weather location, or your IP if you set none | [wttr.in](https://wttr.in) | Every time the dashboard opens |
| Calendar credentials and queries | Your own CalDAV server | Dashboard open, only once you add an account in Full Calendar |
| Feed queries + `CROSSREF_MAILTO` | bioRxiv, Crossref, PubMed | The "What's new?" card, only for feeds you enable |
| Nothing at all | — | Everything else: KPIs, Bayesian forecasting, ops checks, templates, git |

**The AI layer is sandboxed to `03_KNOWLEDGE/`.** `queryFolders` in LLM Wiki's
settings is an allowlist, and it ships containing only that folder, so
`01_PROJECTS`, `02_GRANTS`, `04_PEOPLE`, `05_ADMIN`, `09_PEER_REVIEWS` and the
rest are never read, indexed or sent anywhere — even when the model is hosted.
Widening that allowlist widens what leaves your machine, so widen it knowingly.

**To go fully offline**, pull a local model and change two settings — `AI_MODEL`
in `.env` and the model name in LLM Wiki's settings. Then nothing in the first
five rows leaves your machine. **GET STARTED** walks through it, and if your
notes are sensitive, do it before you start writing.

## Setup

1. Clone this repo and open it as a vault: `File → Open vault → /path/to/HOB`
2. Open **GET STARTED** in the vault root, or click the link in the welcome card on the dashboard. It walks through the first day.
3. Obsidian will prompt about community plugins being present — turn them on (Settings → Community plugins). That's it for the plugins covered above; install any of the optional ones you also want.
4. Copy both env files and fill them in:
   ```bash
   cp .env.example .env                          # read by Templater/dataviewjs (AI_URL, CROSSREF_MAILTO, ...)
   cp _scripts/.env.example _scripts/.env         # read by the Python automations (VAULT_ROOT, ZOTERO_DB, ...)
   ```
5. Set up the Python side:
   ```bash
   cd _scripts
   python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   # optional, only if you use audio transcription:
   pip install -r requirements-transcription.txt
   python3 cron/setup_launchd.py
   python3 ops/health_check.py --no-write   # smoke test
   ```

6. The AI features (Ask-AI search, AI helper card) need [Ollama](https://ollama.com) with a chat model and `nomic-embed-text` for the semantic index. Nothing else in HOB depends on it. HOB ships pointing at a **hosted** model, so decide here whether to keep that or go local — **GET STARTED** walks through both, and [What leaves your machine](#what-leaves-your-machine) says what the choice changes.

## Versioning

HOB ships as a git repository, but that repository is the template. Cloning it leaves `origin` pointing at this repo, and nothing commits on your behalf, so a fresh vault has no backup and no history of its own.

Repoint the remote before you write anything you care about, and keep it private. A research vault holds unpublished work, confidential reviews, and personal data about collaborators.

```bash
git -C /path/to/your/vault remote remove origin
git -C /path/to/your/vault remote add origin git@github.com:you/your-vault.git
```

Downloaded the zip instead of cloning? There is no repository at all, so run `git init` first. The dashboard's Vault Status card reads "Not versioned" whenever that is the case.

For automatic snapshots, install the **Obsidian Git** community plugin. It is not bundled because it installs in two clicks from Obsidian's own registry.

**macOS only.** The scheduler is built on `launchd`; the Python scripts themselves are portable, but running them under cron/systemd on Linux is untested.

## Folder layout

Numbered top-level folders for stable ordering — see the short `README`/hub note in each for what belongs there: `00_STAGING` (inbox), `01_PROJECTS`, `02_GRANTS`, `03_KNOWLEDGE` (literature/concepts/protocols), `04_PEOPLE` (collaborators), `05_ADMIN`, `06_PLANNING` (KPIs), `07_INNOVATION`, `08_TEACHING`, `09_PEER_REVIEWS`, `99_ARCHIVE`. The automations assume this layout — if your own vault uses different names, you'll need to either adopt these or adjust the scripts yourself.

## License

AGPL-3.0 — see [LICENSE](LICENSE). This covers the vault structure, theme, the Sky Background plugin, the dashboard, and all `_scripts/` automation. Use it, study it, change it, sell it if you want; what you may not do is take it closed. Anyone who distributes a modified HOB, or runs one as a network service, has to publish their changes under the same license. It does **not** cover any content you put in your own vault once you start using it, and it does **not** cover the seven third-party plugins bundled under `.obsidian/plugins/`, which keep their own licenses — six MIT and one AGPL-3.0. See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).


## Credits

- Theme and dashboard originally built around [Obsidian](https://obsidian.md/) — HOB is an independent toolkit that runs on top of the stock app, not a modified build of it.
- `home-tab` fork based on [olrenso/obsidian-home-tab](https://github.com/olrenso/obsidian-home-tab) (MIT) by Lorenzo.
- Ask-AI search powered by [llm-wiki](https://github.com/domleca/llm-wiki) (MIT) by Dominique Leca, used through [HOB's fork](https://github.com/Bendlexane/llm-wiki), which adds vault scoping and an inline query API.
- Bundled, unmodified: [Dataview](https://github.com/blacksmithgu/obsidian-dataview), [QuickAdd](https://github.com/chhoumann/quickadd), [Full Calendar](https://github.com/obsidian-community/obsidian-full-calendar) and [Make.md](https://github.com/Make-md/makemd), each MIT-licensed, plus [Templater](https://github.com/SilentVoid13/Templater), which is **AGPL-3.0**. Credit to their respective authors. Every bundled plugin ships its upstream `LICENSE` next to its build, and [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) lists version, license and source for all eight.

## Final note

HOB is free and open source.

There is no subscription, no hosted service required for the core workflow, and no obligation to use every component.

The project is still evolving, and the best way to make it better is to have more researchers actually use it.

If you find HOB useful, give it a try and cite it in your papers as:





If you find something broken, report it. If you have an idea, share it. If you want to build it together, get in touch.

⸻

HOB Research Vault Toolkit

Free · Open Source · Local-first · Built for Researchers