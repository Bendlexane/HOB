# `_scripts/ops/` — Vault self-observability

The *spia motore* of the vault (ADR §24). It does not look at your research; it
looks at whether the automation that feeds your research is still working.
Goal: convert **silent failures** (a cron that has been dead for a week, a typo
that silently drops a note from every query) into one ranked block you read once
a day.

## Components

| File | Role |
|---|---|
| `health_check.py` | Orchestrator. Runs every check, writes a JSON snapshot, prints the `🚨 Automation health` Markdown block. |
| `checks/cron_heartbeat.py` | Did each scheduled job fire on time, and did its last run error out? |
| `checks/frontmatter_lint.py` | Does every typed note still validate against `schemas/*`? |
| `checks/cron_registry.json` | One row per monitored cron job. **Edit this whenever you add a cron.** |
| `schemas/*.schema.yaml` | JSON Schema (draft-07) per note `type`. |
| `logs/YYYY-MM-DD_health.json` | Daily snapshot, 90-day retention. |
| `logs/heartbeat/<name>.txt` | Optional success-heartbeat written by a job after it succeeds. |

## Usage

```bash
python3 _scripts/ops/health_check.py            # the morning block (also writes a snapshot)
python3 _scripts/ops/health_check.py --json     # full machine-readable snapshot
python3 _scripts/ops/health_check.py --strict   # exit 1 if any 🔴 (for monitoring)

python3 _scripts/ops/checks/frontmatter_lint.py # run one check standalone
python3 _scripts/ops/checks/cron_heartbeat.py
```

## Two ways a cron failure is caught

1. **Liveness** — the job did not run within `max_age_hours`. Source: the
   success-heartbeat if present, else the log file mtime.
2. **Health** — the job ran but its log tail contains an error signature
   (`Traceback`, `Operation not permitted`, `❌`, …). This is how a cron that
   runs *and crashes* every day finally gets noticed.

### Success-heartbeat pattern (recommended)

Make a job signal success explicitly, so "fired but failed" ≠ "fired and
succeeded". Chain the beat with `&&` so it only fires on a clean exit:

```cron
0 17 * * * cd <vault> && python3 _scripts/kpi/collector.py >> _scripts/ops/logs/kpi_collector.log 2>&1 \
           && python3 _scripts/ops/checks/cron_heartbeat.py --beat kpi_collector
```

## Scheduling health_check

Run it just before the morning briefing so its output can be spliced in:

```cron
55 7 * * * cd <vault> && python3 _scripts/ops/health_check.py >> _scripts/ops/logs/health_check.log 2>&1
```

## Adding a new check

1. Create `checks/<name>.py` exposing `run() -> list[dict]`, where each finding is
   `{"severity": "red|yellow|info|ok", "check": str, "target": str, "message": str}`.
2. Register it in `health_check.py` → `CHECKS`.
3. (cron jobs only) add a row to `checks/cron_registry.json`.

## Known follow-ups (Phase 1 leftovers from the plan)

Not yet implemented — add when needed: `wetlab_contract.py` (extraction
stability), `plugin_freshness.py` (Obsidian plugin abandonment), `source_drift.py`
(`_project.md.status` vs folder), `adr_self_test.py` (ADR claims vs reality).
