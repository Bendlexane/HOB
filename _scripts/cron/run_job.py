#!/usr/bin/env python3
"""run_job.py — launchd entry wrapper.

Runs one vault script, mirrors its output to the job log under the vault, and
writes a success-heartbeat on a clean exit. The whole chain is pure Python, so
**only the python3.10 binary needs Full Disk Access** — no /bin/sh (a SIP
system binary the Full Disk Access picker refuses to add).

Usage (from launchd):
    python3.10 run_job.py <job_name> <script_rel_to_vault> [--beat NAME] [-- extra args]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
PY = sys.executable
LOGS = VAULT / "_scripts" / "ops" / "logs"
HEARTBEAT = VAULT / "_scripts" / "ops" / "checks" / "cron_heartbeat.py"


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit("usage: run_job.py <job_name> <script_rel> [--beat NAME] [extra...]")

    beat = None
    if "--beat" in args:
        i = args.index("--beat")
        beat = args[i + 1]
        del args[i:i + 2]

    job_name = args[0]
    script = args[1]
    extra = args[2:]

    # cwd=VAULT mirrors the old crontab `cd $VAULT &&` — launchd otherwise
    # starts jobs in `/`, which breaks any CWD-relative path resolution.
    proc = subprocess.run([PY, str(VAULT / script), *extra],
                          cwd=str(VAULT), capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")

    # Job log under the vault (read by cron_heartbeat's error scan). Written by
    # this FDA-covered python, so it succeeds once access is granted.
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        (LOGS / f"{job_name}.log").write_text(output, encoding="utf-8")
    except OSError as e:
        output += f"\n[run_job] could not write job log: {e}\n"

    sys.stdout.write(output)  # also flows to launchd StandardOutPath

    if proc.returncode == 0 and beat:
        subprocess.run([PY, str(HEARTBEAT), "--beat", beat],
                       capture_output=True)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
