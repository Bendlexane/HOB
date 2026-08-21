#!/usr/bin/env python3
"""
Scan 01_PROJECTS/ for _project.md with status: published and move the
entire project folder to 99_ARCHIVE/.

Usage:
    python _scripts/automation/archive_published.py          # real run
    python _scripts/automation/archive_published.py --dry-run # preview only

Expected .env:
    VAULT_ROOT=/absolute/path/to/vault
"""

import argparse
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("archive_published")


def load_env(vault_root_hint: Optional[Path] = None) -> Path:
    """Resolve VAULT_ROOT from .env or fall back to parent of _scripts/."""
    search_dirs = [vault_root_hint] if vault_root_hint else []
    search_dirs += [Path.cwd(), Path(__file__).resolve().parent.parent.parent]

    for d in search_dirs:
        env_path = d / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("VAULT_ROOT="):
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    return Path(val).resolve()

    # Fallback: _scripts/../  (i.e. the vault root)
    return Path(__file__).resolve().parent.parent.parent


def find_project_files(vault_root: Path) -> list[Path]:
    projects_dir = vault_root / "01_PROJECTS"
    if not projects_dir.is_dir():
        logger.warning("01_PROJECTS/ not found at %s", projects_dir)
        return []
    return sorted(projects_dir.rglob("_project.md"))


def parse_status(text: str) -> Optional[str]:
    # Inline: "status: published"
    inline = re.search(r"^status:[ \t]+(\S+)", text, re.MULTILINE)
    if inline:
        return inline.group(1)
    # List format: "status:\n  - published" (Obsidian multitext legacy)
    list_match = re.search(
        r"^status:[ \t]*\n[ \t]+-[ \t]+(\S+)", text, re.MULTILINE
    )
    return list_match.group(1) if list_match else None


def archive_project(project_dir: Path, archive_dir: Path, dry_run: bool) -> bool:
    project_name = project_dir.name
    dest = archive_dir / project_name

    if dest.exists():
        logger.warning("Target exists, skipping: %s", dest)
        return False

    if dry_run:
        logger.info("[DRY-RUN] Would move: %s → %s", project_dir, dest)
        return True

    shutil.move(str(project_dir), str(dest))
    logger.info("Archived: %s → %s", project_dir, dest)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Archive published projects to 99_ARCHIVE/"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    args = parser.parse_args()

    vault_root = load_env()
    logger.info("Vault root: %s", vault_root)

    archive_dir = vault_root / "99_ARCHIVE"
    archive_dir.mkdir(parents=True, exist_ok=True)

    project_files = find_project_files(vault_root)
    archived = 0
    skipped = 0

    for pf in project_files:
        try:
            text = pf.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("Cannot read %s: %s", pf, e)
            skipped += 1
            continue

        status = parse_status(text)
        if status != "published":
            continue

        project_dir = pf.parent
        if archive_project(project_dir, archive_dir, args.dry_run):
            archived += 1

    if args.dry_run:
        logger.info(
            "[DRY-RUN] Complete: %d projects would be archived, %d skipped",
            archived,
            skipped,
        )
    else:
        logger.info(
            "Complete: %d projects archived, %d skipped", archived, skipped
        )

    return 0 if not skipped else 1


if __name__ == "__main__":
    sys.exit(main())
