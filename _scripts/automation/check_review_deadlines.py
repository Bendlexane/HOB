#!/usr/bin/env python3
"""
check_review_deadlines.py — Scan 09_PEER_REVIEWS/ for overdue reviews
and write them to the dashboard Notification Center JSON.

Usage:
    python3 _scripts/automation/check_review_deadlines.py           # check only
    python3 _scripts/automation/check_review_deadlines.py --notify  # check + write to notifications.json
    python3 _scripts/automation/check_review_deadlines.py --json    # machine-readable output
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent.parent
REVIEWS_DIR = VAULT / "09_PEER_REVIEWS"
NOTI_FILE = VAULT / "06_PLANNING/kpis/notifications.json"


def add_notification(
    title: str,
    message: str,
    approve_cmd: str | None = None,
    approve_label: str | None = None,
    approve_running_label: str | None = None,
    approve_success_msg: str | None = None,
) -> None:
    """Append a notification to the dashboard Notification Center JSON."""
    notifications = []
    if NOTI_FILE.exists():
        try:
            with open(NOTI_FILE, "r", encoding="utf-8") as f:
                notifications = json.load(f)
                if not isinstance(notifications, list):
                    notifications = []
        except Exception:
            notifications = []

    # Deduplicate: if an unread notification with same approve_cmd already exists, skip
    if approve_cmd:
        for n in notifications:
            if not n.get("read") and n.get("approve_cmd") == approve_cmd:
                return
    else:
        for n in notifications:
            if not n.get("read") and n.get("title") == title and n.get("message") == message:
                return

    now_ms = int(time.time() * 1000)
    new_noti = {
        "id": f"{now_ms}.{int(time.time() * 100000) % 10000}",
        "title": title,
        "message": message,
        "timestamp": now_ms,
        "read": False,
        "sound": True
    }
    if approve_cmd:
        new_noti["approve_cmd"] = approve_cmd
    if approve_label:
        new_noti["approve_label"] = approve_label
    if approve_running_label:
        new_noti["approve_running_label"] = approve_running_label
    if approve_success_msg:
        new_noti["approve_success_msg"] = approve_success_msg

    notifications.append(new_noti)
    notifications = notifications[-20:]

    try:
        NOTI_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(NOTI_FILE, "w", encoding="utf-8") as f:
            json.dump(notifications, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error writing notification: {e}", file=sys.stderr)


def parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter fields from a markdown file using regex."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    body = m.group(1)
    fields = {}
    for line in body.splitlines():
        # strip comments
        line = line.split('#')[0].strip()
        kv = re.match(r"^(\w+):\s*(.*)", line)
        if kv:
            key = kv.group(1)
            val = kv.group(2).strip().strip('"').strip("'")
            fields[key] = val
    return fields


def check_reviews(notify: bool = False) -> list[dict]:
    today = date.today()
    overdue = []

    for proj_dir in sorted(REVIEWS_DIR.iterdir()):
        if not proj_dir.is_dir() or proj_dir.name.startswith("."):
            continue

        # Load parent metadata if available for journal/manuscript ID
        parent_fm = {}
        for parent_name in ("_peer.md", "_project.md", f"{proj_dir.name}.md"):
            p_file = proj_dir / parent_name
            if p_file.exists():
                try:
                    parent_fm = parse_frontmatter(p_file.read_text(encoding="utf-8"))
                    break
                except Exception:
                    pass

        # 1. Check parent note directly (primary source of truth in reverted design)
        parent_checked = False
        if parent_fm and "review_status" in parent_fm:
            parent_checked = True
            status = parent_fm.get("review_status", "")
            deadline_str = parent_fm.get("deadline", "")
            if status == "in_progress" and deadline_str:
                try:
                    deadline = date.fromisoformat(deadline_str)
                    if deadline < today:
                        journal = parent_fm.get("journal", "?")
                        msid = parent_fm.get("manuscript_id", "?")
                        entry = {
                            "project": proj_dir.name,
                            "journal": journal,
                            "manuscript_id": msid,
                            "deadline": deadline_str,
                            "status": status,
                            "days_overdue": (today - deadline).days,
                        }
                        overdue.append(entry)

                        if notify:
                            proj_name = proj_dir.name
                            python_path = sys.executable or "python3"
                            approve_cmd = f"{python_path} _scripts/automation/complete_review.py --project {proj_name}"
                            add_notification(
                                title="📋 Overdue Peer Review",
                                message=f"Review for {journal} {msid} was due {deadline_str} ({entry['days_overdue']}d overdue)",
                                approve_cmd=approve_cmd,
                                approve_label="Mark Done",
                                approve_running_label="Saving...",
                                approve_success_msg=f"✅ Review for {journal} {msid} marked as done!"
                            )
                except Exception:
                    pass

        # 2. Fallback to checking round folders if not checked in parent note (legacy or temporary architecture folders)
        if not parent_checked:
            for round_dir in sorted(proj_dir.glob("round_*")):
                if not round_dir.is_dir():
                    continue
                round_file = round_dir / f"{round_dir.name}.md"
                if not round_file.exists():
                    continue

                try:
                    text = round_file.read_text(encoding="utf-8")
                    fm = parse_frontmatter(text)
                    status = fm.get("review_status", "")
                    deadline_str = fm.get("deadline", "")

                    if status == "in_progress" and deadline_str:
                        deadline = date.fromisoformat(deadline_str)
                        if deadline < today:
                            journal = fm.get("journal") or parent_fm.get("journal", "?")
                            msid = fm.get("manuscript_id") or parent_fm.get("manuscript_id", "?")
                            entry = {
                                "project": f"{proj_dir.name}/{round_dir.name}",
                                "journal": journal,
                                "manuscript_id": msid,
                                "deadline": deadline_str,
                                "status": status,
                                "days_overdue": (today - deadline).days,
                            }
                            overdue.append(entry)

                            if notify:
                                proj_path = f"{proj_dir.name}/{round_dir.name}"
                                python_path = sys.executable or "python3"
                                approve_cmd = f"{python_path} _scripts/automation/complete_review.py --project {proj_path}"
                                add_notification(
                                    title="📋 Overdue Peer Review",
                                    message=f"Review for {journal} {msid} ({round_dir.name}) was due {deadline_str} ({entry['days_overdue']}d overdue)",
                                    approve_cmd=approve_cmd,
                                    approve_label="Mark Done",
                                    approve_running_label="Saving...",
                                    approve_success_msg=f"✅ Review for {journal} {msid} ({round_dir.name}) marked as done!"
                                )
                except Exception:
                    continue

    return overdue


def main() -> int:
    ap = argparse.ArgumentParser(description="Check for overdue peer reviews")
    ap.add_argument("--notify", action="store_true", help="Write notifications to dashboard JSON")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args()

    overdue = check_reviews(notify=args.notify)

    if args.json:
        print(json.dumps(overdue, indent=2))
        return 0 if not overdue else 1

    if not overdue:
        print("✅ No overdue peer reviews.")
        return 0

    print(f"⚠️  {len(overdue)} overdue review(s):\n")
    for r in overdue:
        print(f"  {r['journal']} {r['manuscript_id']}")
        print(f"    Deadline: {r['deadline']} ({r['days_overdue']}d overdue)")
        print(f"    Project:  {r['project']}")
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
