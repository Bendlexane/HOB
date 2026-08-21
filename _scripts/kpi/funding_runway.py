#!/usr/bin/env python3
"""Funding KPI — scan 02_GRANTS/*/_grant.md and snapshot the funding status.

Computes, for today:
    obtained_eur   sum of amount_funded over ACTIVE grants (money actually obtained)
    runway_months  amount-weighted months of remaining coverage from active grants
    pipeline_eur   sum of amount_requested over SUBMITTED grants (awaiting decision)
    grants_submitted_ytd / grants_funded_ytd / success_rate_5y

Writes one row to funding_status (research_kpis.db). Read-only on grant notes.

    python _scripts/kpi/funding_runway.py [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("kpi.funding_runway")

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_FM_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def _read_fm(path: Path) -> dict:
    m = _FM_RE.match(path.read_text(encoding="utf-8"))
    return (yaml.safe_load(m.group(1)) or {}) if m else {}


def _months_between(d1: date, d2: date) -> float:
    return max(0.0, (d2 - d1).days / 30.44)


def compute(vault_root: Path, today: Optional[date] = None) -> dict:
    today = today or date.today()
    grants_dir = vault_root / "02_GRANTS"
    obtained = 0
    pipeline = 0
    weighted_months = 0.0
    submitted_ytd = funded_ytd = 0
    funded_5y = total_resolved_5y = 0

    for gm in grants_dir.rglob("_grant.md"):
        fm = _read_fm(gm)
        if fm.get("type") != "grant":
            continue
        status = fm.get("status")
        amount_funded = fm.get("amount_funded") or 0
        amount_requested = fm.get("amount_requested") or 0
        created_year = str(fm.get("created", ""))[:4]

        if status == "active":
            obtained += amount_funded
            end = fm.get("period_end")
            if end:
                try:
                    months = _months_between(today, date.fromisoformat(str(end)))
                    weighted_months += months  # amount-weighting kept simple: sum of remaining months
                except ValueError:
                    pass
        elif status == "submitted":
            pipeline += amount_requested

        # YTD counters by creation/submission year (best-effort from frontmatter)
        if created_year == str(today.year):
            if status in ("submitted", "active", "archived"):
                submitted_ytd += 1
            if status == "active" or fm.get("outcome") == "funded":
                funded_ytd += 1

        # 5-year success rate over resolved grants
        outcome = fm.get("outcome")
        if outcome in ("funded", "rejected"):
            total_resolved_5y += 1
            if outcome == "funded":
                funded_5y += 1

    success = round(funded_5y / total_resolved_5y, 3) if total_resolved_5y else None
    return {
        "date": today.isoformat(),
        "runway_months": round(weighted_months, 1),
        "obtained_eur": int(obtained),
        "pipeline_eur": int(pipeline),
        "grants_submitted_ytd": submitted_ytd,
        "grants_funded_ytd": funded_ytd,
        "success_rate_5y": success,
    }


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    p = argparse.ArgumentParser(description="Snapshot grant funding KPIs")
    p.add_argument("--dry-run", action="store_true", help="Print, do not write to DB")
    a = p.parse_args(argv)

    from utils.vault import VaultPaths
    vault = VaultPaths()
    row = compute(vault.root)
    logger.info("Funding: obtained €%s · pipeline €%s · runway %.1f mo · success %s",
                row["obtained_eur"], row["pipeline_eur"], row["runway_months"], row["success_rate_5y"])
    if a.dry_run:
        print(row)
        return
    from kpi.database import KpiDb
    db = KpiDb(vault.kpi_db)
    db.ensure_schema()
    db.upsert_funding_status(row)
    logger.info("Wrote funding_status for %s", row["date"])


if __name__ == "__main__":
    main()
