---
sticker: emoji//1f680
tags:
  - hob/docs
---

A day-one guide to HOB. The [README](README.md) covers installation; this note covers what to actually do once the vault opens.

## First ten minutes

1. **Turn on community plugins.** Settings, then Community plugins, then enable them. The eight bundled plugins activate together and the dashboard needs Dataview among them.
2. **Set your name and location.** The welcome card on `_HOME` asks once. Later you can click your name in the greeting, or the location line under it, to change either.
3. **Fill in the two env files.** Copy `.env.example` to `.env` and `_scripts/.env.example` to `_scripts/.env`. Without `CROSSREF_MAILTO` the journal feed stays hidden, and without `_scripts/.env` none of the Python automations know where the vault lives.
4. **Set up Python.** From `_scripts/`, create a venv, install `requirements.txt`, then run `python3 ops/health_check.py --no-write`. It tells you what is wired and what is not.

Everything else can wait. HOB is usable as a plain vault before a single script runs.

## Where things go

Put a note in the folder matching the *stage of work*, not the topic. Click any folder in the sidebar to open its hub note, which explains what belongs there.

| Folder | Use it for |
|---|---|
| `00_STAGING` | Anything not yet classified. Daily notes, downloads, raw ideas. |
| `01_PROJECTS` | One folder per active research project. |
| `02_GRANTS` | Grant applications moving through writing, submitted, active, archive. |
| `03_KNOWLEDGE` | Literature notes, concepts, methods, protocols. The semantic layer. |
| `04_PEOPLE` | Students and collaborators, plus the coauthor registry. |
| `05_ADMIN` | Bureaucracy, missions, certificates, CV material. |
| `06_PLANNING` | KPIs, monthly plans, annual reports. |
| `07_INNOVATION` | Changes to the system itself. Retrospectives, tech radar. |
| `08_TEACHING` | Courses, seminars, teaching materials. |
| `09_PEER_REVIEWS` | Reviews you are doing for journals. |
| `99_ARCHIVE` | Finished projects, moved here automatically once published. |

Two rules keep this workable. Nothing stays in `00_STAGING` forever, and scientific content never lives in `04_PEOPLE`.

## The dashboard

`_HOME` is one dataviewjs block. Opening it is how you start the day.

| Card | What it gives you |
|---|---|
| Greeting, clock, weather | Click the name or the location to change them. |
| Search bar | Filename search. Press Enter on a question and it goes to the Ask-AI panel instead. |
| Vault Actions | The quick-launch grid. New project, new grant, lab note, peer review, transcription, and the rest. |
| KPI Analytics | Reading and writing stats. Ships with sample data until you run the collector. |
| What's new? | Recent papers from bioRxiv, PubMed, and any journal you add by ISSN. |
| Calendar | Your CalDAV calendars, once configured in Full Calendar's settings. |
| Vault Status | Which automations ran and when. |

## Your first real actions

- **Start a project.** Vault Actions, then New Project. It creates the folder, the frontmatter, and the coauthor links.
- **Take a lab note.** Vault Actions, then Lab Note. It lands in `00_STAGING/_daily/`.
- **Add a journal to the feed.** In the What's new? card, use the `+` chip and paste an ISSN. `Nature Plants` ships as a worked example.

## What runs on its own

`python3 _scripts/cron/setup_launchd.py` installs the scheduler. From then on the vault collects KPIs, ingests Zotero annotations, cleans the wiki, and checks review deadlines every night. Run `python3 _scripts/ops/health_check.py` whenever you want to know whether it is still working.

## When a card looks empty

That is usually configuration, not breakage.

| Card | Likely reason |
|---|---|
| KPI Analytics says "not collected yet" | Run `python3 _scripts/kpi/collector.py` from the vault root. |
| No journal papers | `CROSSREF_MAILTO` is missing from `.env`. |
| Calendar is empty | No calendar sources yet. Add them in Full Calendar's settings. |
| Ask AI answers nothing | It talks to a local Ollama. Start it, or point LLM Wiki at another provider in its settings. |

## Making it yours

The folder names are wired into the Python scripts, so rename them only if you are ready to update `_scripts/` too. Everything else is fair game. The dashboard is markdown you can edit, the theme is one CSS file, and the actions are plain JS modules in `_scripts/actions/`.
