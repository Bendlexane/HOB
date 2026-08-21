"""Extract phase-transition observations from git history of _project.md files.

Strategy
--------
For each _project.md in 01_PROJECTS/ and 99_ARCHIVE/, walk every commit that
touched it. At each commit, parse the `status:` frontmatter value. The
*first commit* at which a given status appears is taken as the entry time
into that phase. The duration of phase X equals the number of calendar days
between first_seen[X] and first_seen[next_phase].

Phases (canonical order):
    data_collection -> drafting -> in_review -> published

Observations whose duration is < MIN_PHASE_DAYS (30) are dropped. This
eliminates registration artifacts (project created in the wrong phase and
immediately corrected within a few days) that would otherwise corrupt the
posterior distribution with unrealistically short durations.

The role is read from the HEAD version of the file (current state) and
collapsed to {lead, not_lead}: coauthor and supervisor both map to not_lead.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


PHASES_ORDER = ["data_collection", "drafting", "in_review", "published"]
PHASE_SHORT = {
    "data_collection": "dc",
    "drafting": "dr",
    "in_review": "ir",
}

# Phases completed in fewer days than this are registration artifacts
# (e.g. project created with wrong status and fixed immediately).
MIN_PHASE_DAYS = 30


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------


_STATUS_INLINE = re.compile(r"^status:[ \t]+(\S+)", re.MULTILINE)
_STATUS_LIST = re.compile(r"^status:[ \t]*\n[ \t]+-[ \t]+(\S+)", re.MULTILINE)
_ROLE_INLINE = re.compile(r"^role:[ \t]+(\S+)", re.MULTILINE)


def parse_status(text: str) -> Optional[str]:
    m = _STATUS_INLINE.search(text)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    m = _STATUS_LIST.search(text)
    return m.group(1).strip().strip('"').strip("'") if m else None


def parse_role(text: str) -> Optional[str]:
    m = _ROLE_INLINE.search(text)
    return m.group(1).strip().strip('"').strip("'") if m else None


def collapse_role(role: Optional[str]) -> Optional[str]:
    if role == "lead":
        return "lead"
    if role in {"coauthor", "supervisor"}:
        return "not_lead"
    return None


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------


def _run_git(args: list[str], cwd: Path) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return res.stdout


@dataclass(frozen=True)
class Commit:
    sha: str
    timestamp_unix: int


def list_commits_for_path(vault_root: Path, file_rel: str) -> list[Commit]:
    """Return commits that touched `file_rel`, ordered chronologically (oldest first).

    --follow tracks renames; --diff-filter=AM keeps Add/Modify (drops pure deletes).
    Format: <sha>@<unix_ts> per line.
    """
    out = _run_git(
        [
            "log",
            "--follow",
            "--diff-filter=AM",
            "--format=%H@%ct",
            "--reverse",
            "--",
            file_rel,
        ],
        cwd=vault_root,
    )
    commits: list[Commit] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or "@" not in line:
            continue
        sha, ts = line.split("@", 1)
        try:
            commits.append(Commit(sha=sha, timestamp_unix=int(ts)))
        except ValueError:
            continue
    return commits


def show_file_at_commit(vault_root: Path, sha: str, file_rel: str) -> Optional[str]:
    """Return file content at a given commit, or None if not present there."""
    try:
        return _run_git(["show", f"{sha}:{file_rel}"], cwd=vault_root)
    except subprocess.CalledProcessError:
        return None


# ---------------------------------------------------------------------------
# Per-project transition extraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Observation:
    project_code: str
    role: str       # "lead" or "not_lead"
    phase: str      # "dc", "dr", "ir"
    duration_days: int


def first_seen_per_status(
    vault_root: Path, file_rel: str, commits: list[Commit]
) -> dict[str, int]:
    """For each canonical status that appears, the unix-ts of the first commit
    in which the file held that status."""
    first: dict[str, int] = {}
    for c in commits:
        text = show_file_at_commit(vault_root, c.sha, file_rel)
        if text is None:
            continue
        status = parse_status(text)
        if status is None or status not in PHASES_ORDER:
            continue
        if status not in first:
            first[status] = c.timestamp_unix
    return first


def durations_from_first_seen(first_seen: dict[str, int]) -> dict[str, int]:
    """Convert first-seen timestamps into per-phase durations (calendar days).

    Returns a dict keyed by *short* phase code (dc/dr/ir). Drops zero-day
    durations (status skipped or set in the same commit as the next).
    """
    durations: dict[str, int] = {}
    for i, phase in enumerate(PHASES_ORDER[:-1]):  # exclude 'published'
        next_phase = PHASES_ORDER[i + 1]
        if phase not in first_seen or next_phase not in first_seen:
            continue
        delta_sec = first_seen[next_phase] - first_seen[phase]
        days = delta_sec // 86400
        if days < MIN_PHASE_DAYS:
            continue
        durations[PHASE_SHORT[phase]] = int(days)
    return durations


def extract_observations(vault_root: Path) -> list[Observation]:
    """Walk all _project.md files in 01_PROJECTS/ and 99_ARCHIVE/."""
    out: list[Observation] = []
    for sub in ("01_PROJECTS", "99_ARCHIVE"):
        base = vault_root / sub
        if not base.is_dir():
            continue
        for pf in sorted(base.rglob("_project.md")):
            project_code = pf.parent.name
            file_rel = str(pf.relative_to(vault_root))
            try:
                head_text = pf.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning("Cannot read %s: %s", file_rel, e)
                continue

            role = collapse_role(parse_role(head_text))
            if role is None:
                logger.info("Skipping %s: no recognised role", project_code)
                continue

            commits = list_commits_for_path(vault_root, file_rel)
            if not commits:
                logger.info("Skipping %s: no git history", project_code)
                continue

            first_seen = first_seen_per_status(vault_root, file_rel, commits)
            durations = durations_from_first_seen(first_seen)
            for phase_short, days in durations.items():
                out.append(
                    Observation(
                        project_code=project_code,
                        role=role,
                        phase=phase_short,
                        duration_days=days,
                    )
                )
    return out
