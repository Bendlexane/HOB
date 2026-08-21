"""
refresh_gantt.py - Re-render Mermaid Gantt blocks for active projects.

Runs daily at 8:10 AM (after update_posteriors.py at 8:05).

For each active _project.md the script:
  1. Reads status, role, and phase_*_start dates from frontmatter.
  2. Computes Gantt dates using today + p50 for the current phase end —
     the same logic as the Templater template. This ensures the Mermaid
     "today" line always falls within the active phase bar regardless of
     how long the project has been running.
  3. Rewrites the %%{init...}%% + gantt block in-place.
  4. Touches the file only if content actually changed.

Design note: the cron script intentionally does NOT ask for human input or
update status. It only adjusts the visual Gantt to stay aligned with today.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PHASE_ORDER = ["data_collection", "drafting", "in_review"]
PHASE_SHORT = {"data_collection": "dc", "drafting": "dr", "in_review": "ir"}

# Maps research_type → phase-1 label. None = no dc phase (2-phase article).
PHASE1_LABEL_MAP: dict[str, str | None] = {
    "Original article":       "Data collection",
    "Short communication":    "Data collection",
    "Brief report":           "Data collection",
    "Case report":            "Documentation",
    "Data paper":             "Data curation",
    "Methodological paper":   "Development & validation",
    "Review article":         "Literature search",
    "Systematic review":      "Search & extraction",
    "Meta-analysis":          "Search & extraction",
    "Perspective paper":      "Concept development",
    "Opinion paper":          "Concept development",
    "Editorial":              None,
    "Letter to the editor":   None,
}


def get_phase_config(research_type: str | None, phase_1_label_override: str | None) -> tuple[list[str], dict[str, str]]:
    """Return (active_phases, phase_labels) for this article type.

    phase_1_label_override comes from the `phase_1_label` frontmatter field
    written by the template — it takes precedence over the map lookup so that
    old projects with a custom label are respected.
    """
    dc_label: str | None
    if phase_1_label_override and phase_1_label_override.lower() != "null":
        dc_label = phase_1_label_override
    else:
        dc_label = PHASE1_LABEL_MAP.get(research_type or "", "Data collection")

    if dc_label is None:
        active = ["drafting", "in_review"]
        labels = {"drafting": "Analysis & writing", "in_review": "Under review"}
    else:
        active = ["data_collection", "drafting", "in_review"]
        labels = {
            "data_collection": dc_label,
            "drafting": "Analysis & writing",
            "in_review": "Under review",
        }
    return active, labels

GANTT_THEME = ""

# Regex that matches the full %%{init...}}%% + gantt block (with optional theme header).
# Note: the init block closes with }}%% (no leading %%), so we match \}\}%% not %%\}\}%%
_GANTT_BLOCK_RE = re.compile(
    r"```mermaid\n(?:%%\{init.*?\}\}%%\n)?gantt\n.*?```",
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Vault root resolution
# ---------------------------------------------------------------------------


def load_vault_root() -> Path:
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("VAULT_ROOT="):
                return Path(line.split("=", 1)[1].strip())
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Posteriors / priors loading
# ---------------------------------------------------------------------------


def load_p50(vault_root: Path, model_role: str) -> dict[str, int]:
    """Return {dc: int, dr: int, ir: int} p50 days for the given role."""
    posteriors_path = vault_root / "_scripts" / "ml" / "posteriors.json"
    priors_path = vault_root / "_scripts" / "ml" / "priors.json"

    def pert_mean(o, ml, p):
        return round((o + 4 * ml + p) / 6)

    if posteriors_path.exists():
        try:
            data = json.loads(posteriors_path.read_text())
            if model_role in data:
                c = data[model_role]
                return {
                    "dc": c["dc"]["p50_days"],
                    "dr": c["dr"]["p50_days"],
                    "ir": c["ir"]["p50_days"],
                }
        except Exception:
            pass

    if priors_path.exists():
        try:
            data = json.loads(priors_path.read_text())
            if model_role in data:
                c = data[model_role]
                return {
                    "dc": pert_mean(**c["dc"]),
                    "dr": pert_mean(**c["dr"]),
                    "ir": pert_mean(**c["ir"]),
                }
        except Exception:
            pass

    return {"dc": 293, "dr": 207, "ir": 136}  # hardcoded fallback


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_after_closing_---).

    Handles the standard YAML --- ... --- block at the top of the file.
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    yaml_block = text[3:end].strip()
    body = text[end + 4:]
    try:
        fm = yaml.safe_load(yaml_block) or {}
    except Exception:
        fm = {}
    return fm, body


def collapse_role(role: Optional[str]) -> str:
    if role == "lead":
        return "lead"
    return "not_lead"


# ---------------------------------------------------------------------------
# Gantt date computation (mirrors new-project.md template logic)
# ---------------------------------------------------------------------------


def _add_days(d: date, n: int) -> date:
    return d + timedelta(days=n)


def compute_gantt(
    status: str,
    phase_starts_raw: dict[str, Optional[str]],
    p50: dict[str, int],
    today: date,
) -> dict:
    """Return {starts: {phase: date}, ends: {phase: date}, proj_start: date, pub_date: date}."""
    if status not in PHASE_ORDER:
        return {}

    current_idx = PHASE_ORDER.index(status)

    # Parse user-provided start dates.
    # PyYAML silently converts bare YYYY-MM-DD values to datetime.date; handle both.
    phase_starts: dict[str, date] = {}
    for ph, raw in phase_starts_raw.items():
        if raw is None:
            continue
        if isinstance(raw, date):
            phase_starts[ph] = raw
        elif isinstance(raw, str) and re.match(r"\d{4}-\d{2}-\d{2}", raw):
            try:
                phase_starts[ph] = date.fromisoformat(raw[:10])
            except ValueError:
                pass

    starts: dict[str, date] = dict(phase_starts)
    ends: dict[str, date] = {}

    # Active phase start
    active_start = starts.get(status, today)
    starts[status] = active_start

    # Forward pass: current phase ends today+p50; future phases chain from there
    cursor = today
    for i in range(current_idx, len(PHASE_ORDER)):
        ph = PHASE_ORDER[i]
        short = PHASE_SHORT[ph]
        if ph not in starts:
            starts[ph] = cursor
        ends[ph] = _add_days(today if i == current_idx else cursor, p50[short])
        cursor = ends[ph]

    # Backward pass: past phases
    for i in range(current_idx - 1, -1, -1):
        ph = PHASE_ORDER[i]
        next_ph = PHASE_ORDER[i + 1]
        short = PHASE_SHORT[ph]
        ends[ph] = starts[next_ph]
        if ph not in starts:
            starts[ph] = _add_days(ends[ph], -p50[short])

    proj_start = starts.get("data_collection", today)
    pub_date = ends.get("in_review", today)

    return {"starts": starts, "ends": ends, "proj_start": proj_start, "pub_date": pub_date}


# ---------------------------------------------------------------------------
# Gantt block rendering
# ---------------------------------------------------------------------------


def render_gantt_block(status: str, gantt: dict, p50: dict, active_phases: list[str], phase_labels: dict[str, str]) -> str:
    if not gantt:
        return ""

    current_idx = active_phases.index(status) if status in active_phases else -1
    starts = gantt["starts"]
    ends = gantt["ends"]
    proj_start = gantt["proj_start"]
    pub_date = gantt["pub_date"]

    lines = []
    for i, ph in enumerate(active_phases):
        label = phase_labels[ph]
        s = starts[ph].isoformat()
        e = ends[ph].isoformat()
        if i < current_idx:
            lines.append(f"    {label}  :done, {s}, {e}")
        elif i == current_idx:
            # Use absolute end date (today + p50) so the Mermaid "today" line
            # always falls inside this bar, not past it.
            lines.append(f"    {label}  :crit, {s}, {e}")
        else:
            lines.append(f"    {label}  :{s}, {e}")

    gantt_items = "\n".join(lines)

    return (
        f"```mermaid\n"
        f"{GANTT_THEME}\n"
        f"gantt\n"
        f"    title Project Timeline\n"
        f"    dateFormat  YYYY-MM-DD\n"
        f"    axisFormat  %b %Y\n\n"
        f"    Project started       :milestone, {proj_start.isoformat()}, 0d\n"
        f"{gantt_items}\n"
        f"    Published              :milestone, {pub_date.isoformat()}, 0d\n"
        f"```"
    )


# ---------------------------------------------------------------------------
# Per-project processing
# ---------------------------------------------------------------------------


def process_project(project_md: Path, vault_root: Path, today: date) -> bool:
    """Return True if the file was updated."""
    text = project_md.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(text)

    status = fm.get("status", "")
    if status not in PHASE_ORDER:
        logger.debug("Skipping %s: status=%s not active", project_md.parent.name, status)
        return False

    role = collapse_role(fm.get("role"))
    p50 = load_p50(vault_root, role)

    research_type = fm.get("research_type")
    phase_1_label_override = fm.get("phase_1_label")
    active_phases, phase_labels = get_phase_config(research_type, phase_1_label_override)

    if status not in active_phases:
        logger.debug("Skipping %s: status=%s not in active phases", project_md.parent.name, status)
        return False

    phase_starts_raw = {
        "data_collection": fm.get("phase_dc_start"),
        "drafting": fm.get("phase_dr_start"),
        "in_review": fm.get("phase_ir_start"),
    }

    gantt = compute_gantt(status, phase_starts_raw, p50, today)
    if not gantt:
        return False

    new_block = render_gantt_block(status, gantt, p50, active_phases, phase_labels)

    match = _GANTT_BLOCK_RE.search(text)
    if not match:
        logger.warning("No Gantt block found in %s — skipping", project_md.parent.name)
        return False

    if match.group(0) == new_block:
        logger.debug("No change for %s", project_md.parent.name)
        return False

    new_text = text[: match.start()] + new_block + text[match.end():]
    project_md.write_text(new_text, encoding="utf-8")
    logger.info("Refreshed Gantt for %s (status=%s)", project_md.parent.name, status)
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    vault_root = load_vault_root()
    today = date.today()
    updated = 0

    for sub in ("01_PROJECTS", "99_ARCHIVE"):
        base = vault_root / sub
        if not base.is_dir():
            continue
        for pf in sorted(base.rglob("_project.md")):
            try:
                if process_project(pf, vault_root, today):
                    updated += 1
            except Exception as e:
                logger.error("Error processing %s: %s", pf, e)

    logger.info("Gantt refresh complete: %d file(s) updated", updated)


if __name__ == "__main__":
    main()
