#!/usr/bin/env python3
"""
complete_review.py — Mark a peer review as completed by updating its frontmatter.

Usage:
    python3 _scripts/automation/complete_review.py --project <project_name_or_path>
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent.parent
REVIEWS_DIR = VAULT / "09_PEER_REVIEWS"
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def update_frontmatter(file_path: Path) -> bool:
    if not file_path.exists():
        print(f"Error: File {file_path} does not exist", file=sys.stderr)
        return False

    text = file_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        print(f"Error: File {file_path} has no valid frontmatter", file=sys.stderr)
        return False

    body = m.group(1)
    lines = body.splitlines()

    # Parse fields
    fields = {}
    for line in lines:
        cleaned = line.split("#")[0].strip()
        kv = re.match(r"^(\w+):\s*(.*)", cleaned)
        if kv:
            fields[kv.group(1)] = kv.group(2).strip().strip('"').strip("'")

    today_str = dt.date.today().isoformat()
    received_date_str = fields.get("received_date")

    days_to_complete = None
    if received_date_str:
        try:
            received_date = dt.date.fromisoformat(received_date_str)
            days_to_complete = (dt.date.today() - received_date).days
        except Exception:
            pass

    new_lines = []
    status_updated = False
    generic_status_updated = False
    submitted_updated = False
    days_updated = False

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        kv = re.match(r"^(\w+):\s*(.*)", stripped)
        if kv:
            key = kv.group(1)
            val = kv.group(2)
            if key == "review_status":
                comment = ""
                if "#" in line:
                    comment = "  " + line.split("#", 1)[1].strip()
                new_lines.append(f"review_status: completed{comment}")
                status_updated = True
            elif key == "status" and val == "in_progress":
                comment = ""
                if "#" in line:
                    comment = "  " + line.split("#", 1)[1].strip()
                new_lines.append(f"status: completed{comment}")
                generic_status_updated = True
            elif key == "submitted_date":
                comment = ""
                if "#" in line:
                    comment = "  " + line.split("#", 1)[1].strip()
                new_lines.append(f"submitted_date: {today_str}{comment}")
                submitted_updated = True
            elif key == "days_to_complete" and days_to_complete is not None:
                comment = ""
                if "#" in line:
                    comment = "  " + line.split("#", 1)[1].strip()
                new_lines.append(f"days_to_complete: {days_to_complete}{comment}")
                days_updated = True
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    if not status_updated:
        new_lines.append("review_status: completed")
    if not submitted_updated:
        new_lines.append(f"submitted_date: {today_str}")
    if not days_updated and days_to_complete is not None:
        new_lines.append(f"days_to_complete: {days_to_complete}")

    new_frontmatter = "---\n" + "\n".join(new_lines) + "\n---"
    new_text = FRONTMATTER_RE.sub(new_frontmatter, text, count=1)
    file_path.write_text(new_text, encoding="utf-8")
    print(f"Successfully updated {file_path.relative_to(VAULT)}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark a peer review as completed.")
    parser.add_argument(
        "--project", required=True, help="Project name or project/round path"
    )
    args = parser.parse_args()

    project_arg = args.project.strip("/")

    # Identify the target file
    target_file = None

    if "round_" in project_arg:
        # Format: <project_dir>/round_X
        parts = project_arg.split("/")
        if len(parts) >= 2:
            proj_name, round_name = parts[0], parts[1]
            target_file = REVIEWS_DIR / proj_name / round_name / f"{round_name}.md"
    else:
        # Format: <project_dir>
        proj_dir = REVIEWS_DIR / project_arg
        if proj_dir.is_dir():
            for name in ("_project.md", "_peer.md", f"{project_arg}.md"):
                candidate = proj_dir / name
                if candidate.exists():
                    target_file = candidate
                    break

    if not target_file or not target_file.exists():
        print(
            f"Error: Could not locate review file for project '{project_arg}'",
            file=sys.stderr,
        )
        return 1

    success = update_frontmatter(target_file)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
