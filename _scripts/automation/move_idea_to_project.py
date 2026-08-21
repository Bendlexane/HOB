#!/usr/bin/env python3
"""Move a project-linked idea to the project's writing fragments folder.

Updates status to '→ project' and sets stage to 'manuscript-fragment'.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def update_metadata(filepath: Path) -> None:
    """Rewrite frontmatter to update status and add stage field."""
    text = filepath.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return
    body = m.group(1)
    lines = body.splitlines()

    status_found = False
    stage_found = False

    new_lines = []
    for line in lines:
        if line.strip().startswith("status:"):
            new_lines.append("status: → project                   # raw | developing | → project")
            status_found = True
        elif line.strip().startswith("stage:"):
            new_lines.append("stage: manuscript-fragment")
            stage_found = True
        else:
            new_lines.append(line)

    if not status_found:
        new_lines.append("status: → project")
    if not stage_found:
        new_lines.append("stage: manuscript-fragment")

    new_frontmatter = "---\n" + "\n".join(new_lines) + "\n---"
    new_text = FRONTMATTER_RE.sub(new_frontmatter, text, count=1)
    filepath.write_text(new_text, encoding="utf-8")


def mark_discarded(filepath: Path) -> None:
    """Rewrite frontmatter to set status to 'discarded'."""
    text = filepath.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return
    lines = m.group(1).splitlines()

    status_found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("status:"):
            new_lines.append("status: discarded                   # raw | developing | → project | discarded")
            status_found = True
        else:
            new_lines.append(line)
    if not status_found:
        new_lines.append("status: discarded")

    new_frontmatter = "---\n" + "\n".join(new_lines) + "\n---"
    new_text = FRONTMATTER_RE.sub(new_frontmatter, text, count=1)
    filepath.write_text(new_text, encoding="utf-8")


def discard_idea(vault: Path, filename: str) -> int:
    """Move an idea to 00_STAGING/ideas/_discarded/ and mark it discarded."""
    src_file = vault / "00_STAGING" / "ideas" / filename
    if not src_file.exists():
        print(f"error: source file {src_file} does not exist", file=sys.stderr)
        return 1

    dest_dir = vault / "00_STAGING" / "ideas" / "_discarded"
    dest_file = dest_dir / filename
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        src_file.rename(dest_file)
        print(f"Discarded: {src_file.name} → {dest_file.relative_to(vault)}")
        mark_discarded(dest_file)
        print(f"Updated metadata for: {dest_file.name}")
    except Exception as e:
        print(f"error during discard: {e}", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote (or discard) a staging idea.")
    parser.add_argument("--file", required=True, help="Idea filename (e.g. 2026-06-12_my-idea.md)")
    parser.add_argument("--project", help="Target project code (required unless --discard)")
    parser.add_argument("--discard", action="store_true", help="Discard the idea instead of promoting it.")
    parser.add_argument("--vault-root", default=".", help="Vault root directory.")
    args = parser.parse_args()

    vault = Path(args.vault_root).resolve()

    if args.discard:
        return discard_idea(vault, args.file)

    if not args.project:
        parser.error("--project is required unless --discard is given")

    src_file = vault / "00_STAGING" / "ideas" / args.file

    if not src_file.exists():
        print(f"error: source file {src_file} does not exist", file=sys.stderr)
        return 1

    dest_dir = vault / "01_PROJECTS" / args.project / "04_writing" / "_fragments"
    dest_file = dest_dir / args.file

    try:
        # Create target _fragments directory if missing
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Move the file
        src_file.rename(dest_file)
        print(f"Moved: {src_file.name} → {dest_file.relative_to(vault)}")
        
        # Update status and stage in frontmatter
        update_metadata(dest_file)
        print(f"Updated metadata for: {dest_file.name}")
        
    except Exception as e:
        print(f"error during move/update: {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
