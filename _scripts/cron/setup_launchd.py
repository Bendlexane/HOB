#!/usr/bin/env python3
"""setup_launchd.py — install the vault's scheduled jobs as launchd LaunchAgents.

Why launchd instead of cron: launchd is the modern macOS scheduler and runs
jobs in the user GUI session with no extra Full Disk Access grant needed, as
long as the vault lives outside a TCC-protected folder like ~/Desktop.

Each job runs under the current Python interpreter by default (pass --python
to pin a specific one, e.g. a venv), and appends a success-heartbeat on clean
exit.

Usage:
    python3 setup_launchd.py            # install + load all agents
    python3 setup_launchd.py --uninstall
    python3 setup_launchd.py --list
    python3 setup_launchd.py --python /path/to/venv/bin/python3
"""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
PY = sys.executable
RUN_JOB = str(VAULT / "_scripts" / "cron" / "run_job.py")
LA_DIR = Path.home() / "Library" / "LaunchAgents"
LAUNCHD_LOGS = Path.home() / "Library" / "Logs" / "research-vault"   # NOT TCC-protected
PREFIX = "com.research-vault"
UID = os.getuid()


def _args(job_name: str, script_rel: str, beat: str | None) -> list[str]:
    """ProgramArguments: pure python (no /bin/sh) so only python3.10 needs FDA."""
    a = [PY, RUN_JOB, job_name, script_rel]
    if beat:
        a += ["--beat", beat]
    return a


# name → (StartCalendarInterval, ProgramArguments)
def _jobs() -> dict[str, tuple[list | dict, list[str]]]:
    return {
        "health_check": (
            {"Hour": 7, "Minute": 55},
            _args("health_check", "_scripts/ops/health_check.py", None),
        ),
        "archive_published": (
            {"Hour": 8, "Minute": 0},
            _args("archive_published", "_scripts/automation/archive_published.py", "archive_published"),
        ),
        "update_posteriors": (
            {"Hour": 8, "Minute": 5},
            _args("update_posteriors", "_scripts/ml/update_posteriors.py", "update_posteriors"),
        ),
        "refresh_gantt": (
            {"Hour": 8, "Minute": 10},
            _args("refresh_gantt", "_scripts/automation/refresh_gantt.py", "refresh_gantt"),
        ),
        "kpi_collector": (
            {"Hour": 17, "Minute": 0},
            _args("kpi_collector", "_scripts/kpi/collector.py", "kpi_collector"),
        ),
        "check_review_deadlines": (
            {"Hour": 9, "Minute": 0},
            [PY, RUN_JOB, "check_review_deadlines", "_scripts/automation/check_review_deadlines.py", "--notify", "--beat", "check_review_deadlines"],
        ),
        "wiki_lint": (
            {"Hour": 17, "Minute": 0},
            _args("wiki_lint", "_scripts/automation/wiki_lint.py", "wiki_lint") + ["--notify"],
        ),
        "check_idea_decay": (
            {"Hour": 17, "Minute": 0},
            _args("check_idea_decay", "_scripts/automation/check_idea_decay.py", "check_idea_decay"),
        ),
        "work_life_balance": (
            [{"Weekday": d, "Hour": 17, "Minute": 0} for d in range(1, 6)],
            [str(VAULT / "_scripts" / "cron" / "work_life_balance.sh")],
        ),
    }



def _label(name: str) -> str:
    return f"{PREFIX}.{name}"


def _plist_path(name: str) -> Path:
    return LA_DIR / f"{_label(name)}.plist"


def _load_plist(path: Path, name: str) -> str:
    subprocess.run(["launchctl", "bootout", f"gui/{UID}", str(path)],
                   capture_output=True)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{UID}", str(path)],
                       capture_output=True, text=True)
    return "loaded" if r.returncode == 0 else f"FAILED: {r.stderr.strip()}"


def _describe_jobs() -> None:
    """Print exactly what is about to be scheduled, before scheduling it."""
    print(f"\nAbout to install {len(_jobs())} LaunchAgents into {LA_DIR}")
    print("They run in your user session — no root, no Full Disk Access prompt —")
    print("and keep running daily until you run this script with --uninstall.\n")
    for name, (cal, program_args) in _jobs().items():
        when = cal if isinstance(cal, dict) else cal[0]
        days = "" if isinstance(cal, dict) else " (Mon–Fri)"
        # _args() builds [python, run_job.py, job_name, script_rel, ...], so the
        # script the job actually runs is at index 3; the shell job has it at 0.
        target = program_args[3] if len(program_args) > 3 else program_args[0]
        print(f"  {when.get('Hour', 0):02d}:{when.get('Minute', 0):02d}{days:<10} "
              f"{_label(name):<38} {target}")
    print()


def _confirm() -> bool:
    """Ask before writing to ~/Library/LaunchAgents, unless told not to."""
    try:
        answer = input("Install these agents? [y/N] ").strip().lower()
    except EOFError:
        # Non-interactive (piped, CI): say no rather than scheduling silently.
        print("Not a terminal — re-run with --yes to install non-interactively.")
        return False
    return answer in ("y", "yes")


def install(assume_yes: bool = False) -> None:
    _describe_jobs()
    if not assume_yes and not _confirm():
        print("Nothing installed.")
        return

    LA_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCHD_LOGS.mkdir(parents=True, exist_ok=True)

    # ── Scheduled jobs ────────────────────────────────────────────────
    for name, (cal, program_args) in _jobs().items():
        label = _label(name)
        plist = {
            "Label": label,
            "ProgramArguments": program_args,
            "StartCalendarInterval": cal,
            "RunAtLoad": False,
            "StandardOutPath": str(LAUNCHD_LOGS / f"{name}.out.log"),
            "StandardErrorPath": str(LAUNCHD_LOGS / f"{name}.err.log"),
        }
        path = _plist_path(name)
        with path.open("wb") as fh:
            plistlib.dump(plist, fh)
        print(f"  {label:40} {_load_plist(path, name)}")

    print(f"\n✓ {len(_jobs())} agents installed in {LA_DIR}")


def uninstall() -> None:
    for name in list(_jobs()):
        path = _plist_path(name)
        subprocess.run(["launchctl", "bootout", f"gui/{UID}", str(path)],
                       capture_output=True)
        if path.exists():
            path.unlink()
        print(f"  removed {_label(name)}")
    print("\n✓ all agents removed")


def list_agents() -> None:
    r = subprocess.run(["launchctl", "print", f"gui/{UID}"],
                       capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if PREFIX in line:
            print(line.strip())


def main() -> int:
    global PY
    ap = argparse.ArgumentParser(description="Install vault jobs as launchd agents")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be scheduled, then exit without installing")
    ap.add_argument("--yes", "-y", action="store_true",
                    help="Skip the confirmation prompt")
    ap.add_argument("--python", help="Python interpreter to run jobs with (default: current interpreter)")
    args = ap.parse_args()
    if args.python:
        PY = args.python
    if args.uninstall:
        uninstall()
    elif args.list:
        list_agents()
    elif args.dry_run:
        _describe_jobs()
        print("Dry run — nothing installed.")
    else:
        install(assume_yes=args.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
