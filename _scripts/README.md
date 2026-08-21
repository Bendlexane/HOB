# `_scripts/` — Vault Automation

Python sub-project managing all vault automations. Versioned together with the vault (same git repo).

## Structure

```
_scripts/
├── kpi/             KPI collector + sub-modules for each data source
├── automation/      Operational pipelines (briefing, whisper, email, OCR, etc.)
├── dashboards/      Layer 1 live + Layer 3 annual report
├── notebooks/       Ad-hoc on-demand analysis (.qmd)
├── ops/             Automation Observability (health checks, schemas, logs)
├── utils/           Path resolution, frontmatter parser, config loader
├── cron/            Setup crontab + template
└── tests/           pytest on critical modules
```

## Initial setup

1. Copy `.env.example` → `.env` and fill in the values
2. Create virtualenv: `python3 -m venv venv && source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Setup scheduler: `python3 cron/setup_launchd.py`
5. Test health check: `python ops/health_check.py --dry-run`

## Current status

**2026-05-09 — first automation active:**
- ✅ `automation/archive_published.py` — scans `01_PROJECTS/` for `status: published` and moves to `99_ARCHIVE/` (cron 8:00)

**2026-05-11 — conference transcription server:**
- ✅ `automation/transcribe_server.py` — HTTP server on `localhost:11435`. Start manually before a conference day: `/usr/bin/python3 _scripts/automation/transcribe_server.py` (use **`/usr/bin/python3`** — the system 3.9.6 where `numpy`/`sounddevice`/`whisper` are installed; the default `python3` on PATH is Homebrew and lacks them). Triggered by Buttons in daily notes via `_scripts/templates/record-session-toggle.md` (single start/stop toggle). Records audio (sounddevice) → Whisper → Ollama cleanup → appends to note under the session heading.

**2026-06-01 — Zotero KPI layer live:**
- ✅ `kpi/zotero_stats.py` — reads Zotero SQLite (`immutable=1`): papers added/annotated, annotations, revisits, and per-topic reading classified via Ollama (`gemma4:latest`) or reused from the Zotero Actions & Tags plugin tag. Categories now include `informatics` (11 total).
- ✅ `kpi/collector.py` — daily orchestrator with `--dry-run` and `--date` backfill. Writes to `06_PLANNING/kpis/research_kpis.db`. **Cron `0 17 * * *`** (logs → `ops/logs/kpi_collector.log`); processes the **previous day** by default. Backfilled 2026-05-25 → 2026-05-31.
- Prompt synced in `kpi/tag_prompt.txt` (disambiguation rules + `informatics` + allometry rule).
- ✅ `kpi/database.py export` — Excel export CLI: `python3 _scripts/kpi/database.py export [--from] [--to] [-o]`. Writes `06_PLANNING/kpis/exports/kpis_<today>.xlsx` (Summary sheet + one dump sheet per table). Needs `pandas` + `openpyxl` (in requirements.txt).
- Deferred (still 0 in DB): ActivityWatch reading time (`aw_client` not installed), `kpi/semantic_scholar.py` (h-index/citations), `funding_runway.py`, `reproducibility.py`.

**Still to implement (recommended order):**

1. `utils/` (config, path resolution) — foundation for everything
2. `automation/daily_briefing.py` — first useful cron
4. `ops/health_check.py` + `ops/checks/frontmatter_lint.py` — observability
5. `automation/whisper_note.py` — generic voice lab notes (distinct from conference recording)
6. Rest on-demand

## Conference workflow setup

Before using the mission template for a conference:

1. Install Python deps: `pip install sounddevice soundfile openai-whisper flask numpy requests`
2. Start the transcription server on the morning of each conference day: `/usr/bin/python3 _scripts/automation/transcribe_server.py` (must be `/usr/bin/python3` — the interpreter that has numpy/sounddevice/whisper; launch it from **Terminal.app** so macOS grants it microphone access)
3. In Obsidian → Templater settings → **Template Hotkeys**, add (these live outside `templates_folder`, so they stay hidden from the insert-template suggester but are still exposable as commands):
   - `_scripts/templates/record-session-toggle.md`      → used by 🎙 Record button (toggle start/stop)
   - `_scripts/templates/regenerate-all-daily-notes.md` → used by 🔄 Regenerate all button
   - `_scripts/templates/regenerate-daily-note.md`      → used by 🔄 Regenerate button
4. Verify the command names in the button blocks match those assigned by Templater/Quick Add (edit `action:` if they differ).

## `.env` variables

See `.env.example` for the full list.

## References

- Root [README.md](../README.md) for the vault-level overview and setup steps.
- Each subfolder here (`kpi/`, `automation/`, `cron/`, `lib/`, `ml/`, `ops/`) has its own README with a script-by-script breakdown.
