#!/usr/bin/env python3
"""Scan 00_STAGING/ideas/ for project-linked ideas older than 30 days.

Sends a promotion proposal notification to the dashboard.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration & Helpers
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, str | list[str]]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    body = m.group(1)
    fields: dict[str, str | list[str]] = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        
        # Simple array parser for related_projects: ["CODE"] or []
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                fields[key] = []
            else:
                fields[key] = [item.strip().strip('"').strip("'") for item in inner.split(",")]
        else:
            fields[key] = val
    return fields


def add_dashboard_notification(
    vault: Path,
    noti_id: str,
    title: str,
    message: str,
    detailed_log: str,
    approve_cmd: str,
    reject_cmd: str,
) -> None:
    noti_file = vault / "06_PLANNING" / "kpis" / "notifications.json"
    notifications = []
    if noti_file.exists():
        try:
            with open(noti_file, "r", encoding="utf-8") as f:
                notifications = json.load(f)
                if not isinstance(notifications, list):
                    notifications = []
        except Exception:
            notifications = []

    now_ms = int(time.time() * 1000)

    # Dedup: remove any existing notification with the same ID to prevent duplication
    notifications = [n for n in notifications if n.get("id") != noti_id]

    new_noti = {
        "id": noti_id,
        "title": title,
        "message": message,
        "detailed_log": detailed_log,
        "approve_cmd": approve_cmd,
        "reject_cmd": reject_cmd,
        "timestamp": now_ms,
        "read": False,
        "sound": True,
    }
    notifications.append(new_noti)
    notifications = notifications[-20:]

    try:
        noti_file.parent.mkdir(parents=True, exist_ok=True)
        with open(noti_file, "w", encoding="utf-8") as f:
            json.dump(notifications, f, indent=2, ensure_ascii=False)
        print(f"Added dashboard notification: {title}")
    except Exception as e:
        print(f"Error writing notification: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main Scan Flow
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Scan for idea note decay.")
    parser.add_argument("--vault-root", default=".", help="Vault root directory.")
    args = parser.parse_args()

    vault = Path(args.vault_root).resolve()
    ideas_dir = vault / "00_STAGING" / "ideas"

    if not ideas_dir.exists():
        print(f"error: {ideas_dir} does not exist", file=sys.stderr)
        return 1

    today = dt.date.today()
    decay_count = 0

    python_bin = sys.executable or "/usr/local/bin/python3"
    move_script = vault / "_scripts" / "automation" / "move_idea_to_project.py"

    for md_file in sorted(ideas_dir.glob("*.md")):
        if md_file.name.startswith("_"):
            continue
        try:
            text = md_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        fm = parse_frontmatter(text)
        created_str = fm.get("created", "")
        projects = fm.get("related_projects", [])
        title = fm.get("title", md_file.stem)

        if not created_str or not isinstance(projects, list) or len(projects) == 0:
            continue

        try:
            created_date = dt.date.fromisoformat(str(created_str))
        except (ValueError, TypeError):
            continue

        age_days = (today - created_date).days

        # Decay alert trigger: linked to a project and aged 30 days or more
        if age_days >= 30:
            project_code = projects[0]
            decay_count += 1
            
            noti_id = f"idea_decay_{md_file.name}"
            noti_title = f"💡 Idea Promotion: {title}"
            message = f"Idea linked to {project_code} has reached 30 days. Move to project fragments?"
            
            target_path = f"01_PROJECTS/{project_code}/04_writing/_fragments/{md_file.name}"
            detailed_log = (
                f"Source: 00_STAGING/ideas/{md_file.name}\n"
                f"Linked Project: {project_code}\n"
                f"Target Destination: {target_path}\n"
                f"Action: Move note and set stage to 'manuscript-fragment'"
            )
            
            approve_cmd = f"{python_bin} {move_script} --file {md_file.name} --project {project_code}"
            reject_cmd = f"{python_bin} {move_script} --file {md_file.name} --discard"

            add_dashboard_notification(
                vault=vault,
                noti_id=noti_id,
                title=noti_title,
                message=message,
                detailed_log=detailed_log,
                approve_cmd=approve_cmd,
                reject_cmd=reject_cmd,
            )

    print(f"Decay check complete. Flagged {decay_count} ideas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
