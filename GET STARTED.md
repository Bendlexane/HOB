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

## Two things HOB does not set up for you

These are the two most common surprises, so they are worth doing early.

### Versioning is not automatic

HOB arrives as a git repository, but that repository is the *template*. Its `origin` points at the HOB repo, not at anything of yours, and nothing commits on your behalf. So out of the box your notes have no backup and no history.

Point it somewhere of your own before you write anything you care about.

```bash
git -C /path/to/your/vault remote remove origin
git -C /path/to/your/vault remote add origin git@github.com:you/your-vault.git
```

If you downloaded HOB as a zip rather than cloning it, there is no repository at all. Run `git init` first. The Vault Status card reads "Not versioned" whenever that is the case, so you can tell at a glance.

For automatic timestamped snapshots, install the **Obsidian Git** community plugin. It is not bundled because it is in Obsidian's official registry and installs in two clicks. Set it to commit on an interval and your vault backs itself up while you work.

One warning worth repeating. A research vault holds unpublished work, reviews under confidentiality, and personal data about collaborators. Keep that remote private.

### The AI features need Ollama

Two features talk to a language model, the Ask-AI search bar and the AI helper card. Neither works until Ollama is installed. Everything else in HOB works without it.

This is the part HOB cannot do for you, so here is the whole thing.

**1. Install Ollama.** Download it from [ollama.com](https://ollama.com), or on macOS run `brew install ollama`. Then start it, either by opening the app or with `ollama serve` in a terminal. It listens on `http://localhost:11434`.

**2. Pull the embedding model.** The Ask-AI search builds a semantic index of your notes and needs this one regardless of which chat model you pick.

```bash
ollama pull nomic-embed-text
```

**3. Pick a chat model.** Two routes, and you can change your mind later.

*Hosted, more capable.* `gpt-oss:120b-cloud` runs on Ollama's servers, so it needs a free account but no GPU of your own. This is what HOB ships pointing at.

```bash
ollama signin
ollama pull gpt-oss:120b-cloud
```

*Local, fully offline.* Slower and less capable, but nothing leaves your machine and no account is involved. Good if your notes are sensitive.

```bash
ollama pull qwen2.5:7b
```

**4. Check it worked.**

```bash
ollama list
```

The model you pulled should appear. Hosted models show a size of `-` because they are not stored locally.

**5. Tell HOB which model to use.** Set `AI_MODEL` in the vault-root `.env`, and put the same name in LLM Wiki's settings under Settings, Community plugins, LLM Wiki. If you went local, both become `qwen2.5:7b`. `AI_URL` only needs changing if Ollama is not on the default port, or if you are pointing at some other Ollama-compatible server.

Reopen `_HOME` afterwards. If something is still off, the helper card now names the cause rather than just failing, so it will say whether the server is unreachable or the model is missing.

Being honest about where this stands: HOB is beta, and this is the one part that is not out of the box.

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
| Ask AI answers nothing | Ollama is not running, or a model is not pulled. See the Ollama guide above. |
| Vault Status says "Not versioned" | The vault is not a git repository yet. See the versioning section above. |

## Making it yours

The folder names are wired into the Python scripts, so rename them only if you are ready to update `_scripts/` too. Everything else is fair game. The dashboard is markdown you can edit, the theme is one CSS file, and the actions are plain JS modules in `_scripts/actions/`.
