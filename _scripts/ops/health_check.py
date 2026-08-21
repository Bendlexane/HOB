#!/usr/bin/env python3
"""health_check.py — single entry point for vault self-observability.

Runs every registered check, aggregates findings by severity, and emits:
  1. a machine-readable snapshot  ops/logs/YYYY-MM-DD_health.json  (90-day retention)
  2. a human-readable "🚨 Automation health" Markdown block on stdout, ready to
     be spliced into the morning briefing (daily_briefing.py, when it lands).

This is the spia-motore of the vault (ADR §24): it converts invisible,
days-long silent failures into one ranked block you read once a day.

Usage:
    python3 health_check.py               # print the markdown block
    python3 health_check.py --json        # print the full aggregated snapshot
    python3 health_check.py --strict      # exit 1 if any 🔴 finding (for CI/monitoring)

Cron (before the 08:00 briefing):
    55 7 * * * cd <vault> && python3 _scripts/ops/health_check.py \\
               >> _scripts/ops/logs/health_check.log 2>&1
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

# Make _scripts importable regardless of cwd.
OPS_DIR = Path(__file__).resolve().parent                 # _scripts/ops
sys.path.insert(0, str(OPS_DIR.parent))                   # _scripts

from checks import cron_heartbeat, frontmatter_lint        # noqa: E402

LOGS_DIR = OPS_DIR / "logs"
RETENTION_DAYS = 90
SEVERITY_ORDER = ["red", "yellow", "info", "ok"]
ICON = {"red": "🔴", "yellow": "🟡", "info": "ℹ️", "ok": "✅"}

# Each registered check exposes run() -> list[finding dict].
CHECKS = [
    ("cron_heartbeat", cron_heartbeat.run),
    ("frontmatter_lint", frontmatter_lint.run),
]


def gather() -> list[dict]:
    findings: list[dict] = []
    for name, fn in CHECKS:
        try:
            findings.extend(fn())
        except Exception as e:  # a check must never take the whole report down
            findings.append({
                "severity": "red", "check": name, "target": name,
                "message": f"check itself crashed: {type(e).__name__}: {e}",
            })
    return findings


def _sort_key(f: dict):
    return (SEVERITY_ORDER.index(f["severity"]) if f["severity"] in SEVERITY_ORDER else 99,
            f.get("check", ""), f.get("target", ""))


def render_markdown(findings: list[dict]) -> str:
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_ORDER}
    actionable = [f for f in findings if f["severity"] in ("red", "yellow")]

    lines = ["## 🚨 Automation health"]
    if not actionable:
        lines.append(f"✅ All clear — {counts['ok']} checks healthy, "
                     f"{counts['info']} notes.")
    else:
        head = []
        if counts["red"]:
            head.append(f"{counts['red']} 🔴")
        if counts["yellow"]:
            head.append(f"{counts['yellow']} 🟡")
        lines.append(f"_{', '.join(head)} need attention._")
        lines.append("")
        for f in sorted(actionable, key=_sort_key):
            lines.append(f"- {ICON[f['severity']]} **{f['check']}** · `{f['target']}` — {f['message']}")
    # Info lines (summaries) appended quietly.
    for f in findings:
        if f["severity"] == "info":
            lines.append(f"- {ICON['info']} {f['message']}")
    return "\n".join(lines) + "\n"


def write_snapshot(findings: list[dict]) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_ORDER}
    snapshot = {
        "date": today,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "counts": counts,
        "ok": counts["red"] == 0,
        "findings": sorted(findings, key=_sort_key),
    }
    path = LOGS_DIR / f"{today}_health.json"
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    _prune_old_snapshots()
    return path


def _prune_old_snapshots() -> None:
    cutoff = dt.date.today() - dt.timedelta(days=RETENTION_DAYS)
    for p in LOGS_DIR.glob("*_health.json"):
        try:
            d = dt.date.fromisoformat(p.name[:10])
        except ValueError:
            continue
        if d < cutoff:
            p.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Aggregate vault health checks")
    ap.add_argument("--json", action="store_true", help="Print the full snapshot as JSON")
    ap.add_argument("--strict", action="store_true", help="Exit 1 if any 🔴 finding")
    ap.add_argument("--no-write", action="store_true", help="Do not write the JSON snapshot")
    args = ap.parse_args()

    findings = gather()
    if not args.no_write:
        write_snapshot(findings)

    if args.json:
        print(json.dumps(sorted(findings, key=_sort_key), indent=2, ensure_ascii=False))
    else:
        print(render_markdown(findings), end="")

    has_red = any(f["severity"] == "red" for f in findings)
    return 1 if (args.strict and has_red) else 0


if __name__ == "__main__":
    sys.exit(main())
