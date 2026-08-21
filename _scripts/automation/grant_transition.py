#!/usr/bin/env python3
"""Atomically transition a grant between lifecycle states.

States live as sub-folders of 02_GRANTS/: writing → submitted → active → archive.
A single command keeps the filesystem, the _grant.md frontmatter, linked
projects, and the KPI database in sync — avoiding the drift of doing it by hand.

    python _scripts/automation/grant_transition.py GRANT_2026_MSCA_PLUMBAGO --to submitted
    python _scripts/automation/grant_transition.py GRANT_2026_MSCA_PLUMBAGO --to active \
        --funded 173000 --period-start 2026-09-01 --period-end 2028-08-31
    python _scripts/automation/grant_transition.py GRANT_2026_MSCA_PLUMBAGO --to archive --outcome rejected

Note: 02_GRANTS/archive/ is the resting place for grants (rejected/expired).
99_ARCHIVE/ is only for completed *projects* (01_PROJECTS/) — different things.

On the move to `submitted` the latest evaluator fit_score is frozen into
grant_fit_history as the baseline for a future P(win | score) model.
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("grant_transition")

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

STATE_FOLDER = {"writing": "writing", "submitted": "submitted",
                "active": "active", "archived": "archive"}
TO_ALIASES = {"archive": "archived"}
_FM_RE = re.compile(r"^(---\n)(.*?)(\n---)", re.DOTALL)


def load_env() -> Path:
    for d in (Path.cwd(), _SCRIPTS.parent):
        env = d / "_scripts" / ".env"
        env = env if env.exists() else d / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                line = line.strip()
                if line.startswith("VAULT_ROOT="):
                    return Path(line.split("=", 1)[1].strip().strip("\"'")).resolve()
    return _SCRIPTS.parent


def find_grant(vault_root: Path, code: str) -> Optional[Path]:
    for gm in (vault_root / "02_GRANTS").rglob("_grant.md"):
        m = _FM_RE.match(gm.read_text(encoding="utf-8"))
        if m and (yaml.safe_load(m.group(2)) or {}).get("code") == code:
            return gm
    return None


def update_frontmatter(path: Path, updates: dict) -> None:
    text = path.read_text(encoding="utf-8")
    m = _FM_RE.match(text)
    fm = yaml.safe_load(m.group(2)) or {}
    fm.update(updates)
    dumped = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip("\n")
    path.write_text(text[:m.start()] + f"---\n{dumped}\n---" + text[m.end():], encoding="utf-8")


def propagate_linked_grant(vault_root: Path, code: str, linked_projects: list, dry_run: bool) -> int:
    n = 0
    for proj in linked_projects or []:
        pm = vault_root / "01_PROJECTS" / proj / "_project.md"
        if not pm.exists():
            continue
        m = _FM_RE.match(pm.read_text(encoding="utf-8"))
        if not m:
            continue
        fm = yaml.safe_load(m.group(2)) or {}
        if fm.get("linked_grant") == code:
            continue
        if dry_run:
            logger.info("[DRY-RUN] Would set linked_grant=%s on %s", code, proj)
        else:
            update_frontmatter(pm, {"linked_grant": code})
        n += 1
    return n


def notify_center(vault_root: Path, title: str, message: str, sound: bool = True) -> None:
    """Append a notification to the dashboard notification center (06_PLANNING/kpis/notifications.json)."""
    import json
    import time
    path = vault_root / "06_PLANNING" / "kpis" / "notifications.json"
    try:
        items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(items, list):
            items = []
    except Exception:
        items = []
    items.append({
        "id": f"{int(time.time()*1000)}",
        "title": title,
        "message": message,
        "timestamp": int(time.time() * 1000),
        "read": False,
        "sound": sound,
    })
    items = items[-20:]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items, indent=2), encoding="utf-8")
        logger.info("Notification posted: %s", title)
    except Exception as e:
        logger.warning("Could not write notification center: %s", e)


def freeze_baseline(code: str, fit: dict, outcome: Optional[str]) -> None:
    try:
        from utils.vault import VaultPaths
        from kpi.database import KpiDb
        db = KpiDb(VaultPaths().kpi_db)
        db.ensure_schema()
        if fit and fit.get("overall") is not None:
            db.record_grant_fit(code, fit.get("updated") or date.today().isoformat(),
                                fit.get("overall"), fit.get("excellence"),
                                fit.get("impact"), fit.get("implementation"), 1)
            logger.info("Froze fit baseline for %s (overall %s)", code, fit.get("overall"))
        if outcome:
            db.set_grant_outcome(code, outcome)
    except Exception as e:
        logger.warning("Could not update KPI DB: %s", e)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    p = argparse.ArgumentParser(description="Transition a grant between lifecycle states")
    p.add_argument("code")
    p.add_argument("--to", required=True, choices=["writing", "submitted", "active", "archive"])
    p.add_argument("--funded", type=int, default=None, help="amount_funded (for --to active)")
    p.add_argument("--period-start", default=None)
    p.add_argument("--period-end", default=None)
    p.add_argument("--outcome", choices=["funded", "rejected", "withdrawn"], default=None)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)

    vault_root = load_env()
    target_status = TO_ALIASES.get(a.to, a.to)
    gm = find_grant(vault_root, a.code)
    if not gm:
        logger.error("Grant not found: %s", a.code)
        return 1

    fm = yaml.safe_load(_FM_RE.match(gm.read_text(encoding="utf-8")).group(2)) or {}
    src_dir = gm.parent
    dest_dir = vault_root / "02_GRANTS" / STATE_FOLDER[target_status] / src_dir.name

    if dest_dir.exists() and dest_dir != src_dir:
        logger.error("Target already exists: %s", dest_dir)
        return 1

    logger.info("%s: %s → %s", a.code, fm.get("status"), target_status)

    updates = {"status": target_status}
    if a.funded is not None:
        updates["amount_funded"] = a.funded
    if a.period_start:
        updates["period_start"] = a.period_start
    if a.period_end:
        updates["period_end"] = a.period_end
    if a.outcome:
        updates["outcome"] = a.outcome

    if a.dry_run:
        logger.info("[DRY-RUN] Would set %s and move %s → %s", updates, src_dir, dest_dir)
        propagate_linked_grant(vault_root, a.code, fm.get("linked_projects"), True)
        return 0

    update_frontmatter(gm, updates)
    if dest_dir != src_dir:
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_dir), str(dest_dir))
        logger.info("Moved → %s", dest_dir)

    propagate_linked_grant(vault_root, a.code, fm.get("linked_projects"), False)

    if target_status == "submitted":
        freeze_baseline(a.code, fm.get("fit_score") or {}, None)
    if a.outcome:
        freeze_baseline(a.code, fm.get("fit_score") or {}, a.outcome)

    if target_status == "archived":
        title = fm.get("title") or a.code
        msg = {"funded": f"🏆 Grant completed & funded: {title}",
               "rejected": f"Grant archived (rejected): {title}",
               "withdrawn": f"Grant archived (withdrawn): {title}"}.get(
                   a.outcome, f"Grant archived: {title}")
        notify_center(vault_root, "Grant archived", msg, sound=(a.outcome == "funded"))

    logger.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
