"""Git statistics collector for KPI pipeline.

Extracts word counts, note counts, and commit metrics from local Git repository.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("kpi.git_stats")


def get_commits_for_date(vault_root: Path, target_date: str) -> list[str]:
    """Return a list of commit hashes authored on the target date."""
    # target_date format: YYYY-MM-DD
    # Query commits from YYYY-MM-DD 00:00:00 to YYYY-MM-DD 23:59:59
    start = f"{target_date} 00:00:00"
    end = f"{target_date} 23:59:59"
    try:
        res = subprocess.run(
            [
                "git",
                "log",
                f"--since={start}",
                f"--until={end}",
                "--no-merges",
                "--format=%H",
            ],
            cwd=vault_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return [sha.strip() for sha in res.stdout.splitlines() if sha.strip()]
    except subprocess.CalledProcessError as e:
        logger.error("Failed to run git log: %s", e.stderr)
        return []


def collect(vault_root: Path, target_date: str) -> dict:
    """Collect Git statistics for the target date."""
    commits = get_commits_for_date(vault_root, target_date)
    if not commits:
        logger.info("No commits found for date: %s", target_date)
        return {
            "words_written": 0,
            "words_added": 0,
            "words_removed": 0,
            "notes_created": 0,
            "notes_modified": 0,
            "commits_count": 0,
        }

    words_added = 0
    words_removed = 0
    created_notes: set[str] = set()
    modified_notes: set[str] = set()

    for commit in commits:
        # Determine note creation / modification
        try:
            res = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", commit],
                cwd=vault_root,
                check=True,
                capture_output=True,
                text=True,
            )
            for line in res.stdout.splitlines():
                parts = line.strip().split("\t", 1)
                if len(parts) != 2:
                    continue
                status, filepath = parts
                if filepath.endswith(".md"):
                    if "A" in status:
                        created_notes.add(filepath)
                    elif "M" in status or "T" in status:
                        modified_notes.add(filepath)
        except subprocess.CalledProcessError as e:
            logger.error("Failed to run diff-tree for commit %s: %s", commit, e.stderr)
            continue

        # Find all files with target extensions changed in this commit
        target_files = []
        try:
            res = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit],
                cwd=vault_root,
                check=True,
                capture_output=True,
                text=True,
            )
            for line in res.stdout.splitlines():
                filepath = line.strip()
                if filepath.endswith((".md", ".tex", ".qmd")):
                    target_files.append(filepath)
        except subprocess.CalledProcessError as e:
            logger.error("Failed to list target files for commit %s: %s", commit, e.stderr)
            continue

        if not target_files:
            continue

        # Get parent commit; if root, use empty tree hash
        parent = f"{commit}~1"
        try:
            subprocess.run(
                ["git", "rev-parse", "--verify", parent],
                cwd=vault_root,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            parent = "4b825dc642cb6eb9a030e54d51f65d34b8eacfa3"

        # Calculate word counts from diff
        try:
            diff_res = subprocess.run(
                [
                    "git",
                    "diff",
                    "-U0",
                    parent,
                    commit,
                    "--",
                    *target_files,
                ],
                cwd=vault_root,
                check=True,
                capture_output=True,
                text=True,
            )
            for line in diff_res.stdout.splitlines():
                if line.startswith("+++") or line.startswith("---"):
                    continue
                if line.startswith("+"):
                    text = line[1:].strip()
                    if text:
                        words_added += len(text.split())
                elif line.startswith("-"):
                    text = line[1:].strip()
                    if text:
                        words_removed += len(text.split())
        except subprocess.CalledProcessError as e:
            logger.error("Failed to run diff for commit %s: %s", commit, e.stderr)

    # Ensure a note isn't counted as both created and modified on the same day
    modified_notes = modified_notes - created_notes

    return {
        "words_written": words_added - words_removed,
        "words_added": words_added,
        "words_removed": words_removed,
        "notes_created": len(created_notes),
        "notes_modified": len(modified_notes),
        "commits_count": len(commits),
    }
