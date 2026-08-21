#!/usr/bin/env python3
"""cron_heartbeat.py — detect silent failures of scheduled jobs.

Two failure modes are caught:

  1. LIVENESS  — the job did not fire within `max_age_hours`.
                 Source of truth: an explicit success-heartbeat file
                 (ops/logs/heartbeat/<beat>.txt) if present, otherwise the
                 mtime of the job's log file (proves it *fired*, not that it
                 *succeeded*).
  2. HEALTH    — the job fired but its log tail contains an error signature
                 (traceback, "Operation not permitted", ❌, …). This is how a
                 cron that runs every day but crashes every day gets noticed.

Registry: ops/checks/cron_registry.json (one row per monitored job).

Usage:
    python3 cron_heartbeat.py                 # print findings, human-readable
    python3 cron_heartbeat.py --json          # machine-readable findings
    python3 cron_heartbeat.py --beat NAME     # write a success heartbeat for NAME

Heartbeat pattern (recommended in crontab — beat only on success):
    0 17 * * * python3 .../kpi/collector.py >> .../kpi_collector.log 2>&1 \\
               && python3 .../ops/checks/cron_heartbeat.py --beat kpi_collector
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

OPS_DIR = Path(__file__).resolve().parent.parent          # _scripts/ops
LOGS_DIR = OPS_DIR / "logs"
HEARTBEAT_DIR = LOGS_DIR / "heartbeat"
REGISTRY = Path(__file__).resolve().parent / "cron_registry.json"

# High-precision error signatures. Curated to avoid false positives on the
# word "error" appearing in benign output. Matched case-insensitively.
ERROR_PATTERNS = [
    r"traceback \(most recent call last\)",
    r"operation not permitted",
    r"permission denied",
    r"can't open file",
    r"no such file or directory",
    r"modulenotfounderror",
    r"command not found",
    r"fatal:",
    r"❌",
    r"unhandled exception",
]
_ERROR_RE = re.compile("|".join(ERROR_PATTERNS), re.IGNORECASE)

TAIL_LINES = 40  # how many trailing log lines to scan for error signatures


def _now() -> dt.datetime:
    return dt.datetime.now()


def write_beat(name: str) -> Path:
    """Record a success heartbeat for `name` (called by a job after it succeeds)."""
    HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
    path = HEARTBEAT_DIR / f"{name}.txt"
    path.write_text(_now().isoformat(timespec="seconds") + "\n", encoding="utf-8")
    return path


def _age_hours(ts: dt.datetime) -> float:
    return (_now() - ts).total_seconds() / 3600.0


def _last_run(job: dict) -> tuple[dt.datetime | None, str]:
    """Return (timestamp, source) of the job's last run, or (None, reason)."""
    beat = HEARTBEAT_DIR / f"{job.get('beat', job['name'])}.txt"
    if beat.exists():
        try:
            ts = dt.datetime.fromisoformat(beat.read_text(encoding="utf-8").strip())
            return ts, "success-heartbeat"
        except (ValueError, OSError):
            pass
    log = LOGS_DIR / job["log"]
    if log.exists():
        return dt.datetime.fromtimestamp(log.stat().st_mtime), "log-mtime"
    return None, "no log, no heartbeat"


def _log_errors(job: dict) -> list[str]:
    """Return matched error lines from the tail of the job's log (most recent run)."""
    log = LOGS_DIR / job["log"]
    if not log.exists():
        return []
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    hits = [ln.strip() for ln in lines[-TAIL_LINES:] if _ERROR_RE.search(ln)]
    return hits


def run() -> list[dict]:
    """Check every registered job. Returns a list of finding dicts."""
    findings: list[dict] = []
    if not REGISTRY.exists():
        return [{
            "severity": "red", "check": "cron_heartbeat",
            "target": str(REGISTRY), "message": "cron registry not found",
        }]
    jobs = json.loads(REGISTRY.read_text(encoding="utf-8"))["jobs"]

    for job in jobs:
        name = job["name"]
        critical = job.get("critical", True)
        stale_sev = "red" if critical else "yellow"
        ts, source = _last_run(job)

        # 1. Liveness
        if ts is None:
            findings.append({
                "severity": stale_sev, "check": "cron_heartbeat", "target": name,
                "message": f"never ran — {source} (expected schedule '{job.get('schedule', '?')}')",
            })
        else:
            age = _age_hours(ts)
            if age > job["max_age_hours"]:
                findings.append({
                    "severity": stale_sev, "check": "cron_heartbeat", "target": name,
                    "message": (f"no heartbeat for {age:.0f}h "
                                f"(limit {job['max_age_hours']}h, via {source}) "
                                f"— check launchd/crontab"),
                })

        # 2. Health — error signatures in the last run, even if it fired on time.
        errors = _log_errors(job)
        if errors:
            sample = errors[-1][:160]
            findings.append({
                "severity": "red", "check": "cron_heartbeat", "target": name,
                "message": f"ran but log shows an error: \"{sample}\"",
            })

        if ts is not None and _age_hours(ts) <= job["max_age_hours"] and not errors:
            findings.append({
                "severity": "ok", "check": "cron_heartbeat", "target": name,
                "message": f"healthy (last run {_age_hours(ts):.0f}h ago via {source})",
            })

    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect silent failures of cron jobs")
    ap.add_argument("--beat", metavar="NAME", help="Write a success heartbeat for NAME and exit")
    ap.add_argument("--json", action="store_true", help="Emit findings as JSON")
    args = ap.parse_args()

    if args.beat:
        path = write_beat(args.beat)
        print(f"✓ heartbeat written: {path}")
        return 0

    findings = run()
    if args.json:
        print(json.dumps(findings, indent=2, ensure_ascii=False))
        return 0

    icon = {"red": "🔴", "yellow": "🟡", "info": "ℹ️", "ok": "✅"}
    for f in sorted(findings, key=lambda x: ["red", "yellow", "info", "ok"].index(x["severity"])):
        print(f"{icon.get(f['severity'], '?')} {f['target']}: {f['message']}")
    has_red = any(f["severity"] == "red" for f in findings)
    return 1 if has_red else 0


if __name__ == "__main__":
    sys.exit(main())
