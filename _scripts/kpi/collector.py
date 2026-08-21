#!/usr/bin/env python3
"""Daily KPI orchestrator.

Runs all kpi/ submodules and populates research_kpis.db.
Intended to be called by cron at 8:00.

Usage:
    python _scripts/kpi/collector.py
    python _scripts/kpi/collector.py --date 2026-05-30   # backfill
    python _scripts/kpi/collector.py --dry-run            # preview only
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure _scripts/ is on the path for sibling imports
_SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from utils.config import load as load_config
from utils.vault import VaultPaths

logger = logging.getLogger("kpi.collector")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily KPI collector")
    parser.add_argument(
        "--date",
        default=None,
        help="Target date YYYY-MM-DD (default: yesterday)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be collected without writing to DB",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    cfg = load_config()
    vault = VaultPaths()
    target = args.date or (date.today() - timedelta(days=1)).isoformat()

    logger.info("Collecting KPIs for %s", target)

    vault.ensure_kpi_dir()

    # Conditionally import modules that exist
    report: dict[str, object] = {"date": target}

    try:
        from kpi.zotero_stats import collect as collect_zotero

        zotero_db = Path(cfg["ZOTERO_DB"])
        ollama_host = cfg.get("OLLAMA_HOST", "http://localhost:11434")
        ollama_model = cfg.get("OLLAMA_MODEL", "gemma4:latest")

        zotero_result = collect_zotero(
            zotero_db=zotero_db,
            tag_prompt_path=vault.tag_prompt,
            target=target,
            ollama_host=ollama_host,
            ollama_model=ollama_model,
        )
        report["zotero"] = zotero_result
        logger.info(
            "Zotero: +%d papers, %d annotated, %d revisited",
            zotero_result["papers_added"],
            zotero_result["papers_annotated"],
            zotero_result["papers_revisited"],
        )
    except ImportError:
        logger.warning("zotero_stats.py not available, skipping")
    except Exception:
        logger.exception("Zotero collection failed")
        report["zotero"] = {"error": str(sys.exc_info()[1])}

    try:
        from kpi.git_stats import collect as collect_git

        git_result = collect_git(
            vault_root=vault.root,
            target_date=target,
        )
        report["git"] = git_result
        logger.info(
            "Git: +%d words written (%d added, %d removed), %d commits, %d notes created, %d modified",
            git_result["words_written"],
            git_result["words_added"],
            git_result["words_removed"],
            git_result["commits_count"],
            git_result["notes_created"],
            git_result["notes_modified"],
        )
    except ImportError:
        logger.warning("git_stats.py not available, skipping")
    except Exception:
        logger.exception("Git collection failed")
        report["git"] = {"error": str(sys.exc_info()[1])}

    if args.dry_run:
        print(json.dumps(report, indent=2, default=str))
        return

    from kpi.database import KpiDb

    db = KpiDb(vault.kpi_db)
    db.ensure_schema()

    kpi_payload = {"date": target}

    if "zotero" in report and "error" not in report.get("zotero", {}):
        z = report["zotero"]
        kpi_payload["papers_added_zotero"] = z["papers_added"]
        kpi_payload["papers_annotated_zotero"] = z["papers_annotated"]
        db.upsert_reading_by_topic(z["topics"])
        db.upsert_reading_depth({
            "date": target,
            **z["reading_depth"],
        })

    if "git" in report and "error" not in report.get("git", {}):
        g = report["git"]
        kpi_payload.update({
            "words_written": g["words_written"],
            "words_added": g["words_added"],
            "words_removed": g["words_removed"],
            "notes_created": g["notes_created"],
            "notes_modified": g["notes_modified"],
            "commits_count": g["commits_count"],
        })

    if len(kpi_payload) > 1:
        db.upsert_kpi_daily(kpi_payload)

    try:
        from kpi.export_json import export_kpi_to_json
        export_kpi_to_json(vault.kpi_db, vault.kpi_db.parent / "kpi_data.json")
    except Exception:
        logger.exception("Failed to export KPI data to JSON")

    logger.info("Collection complete for %s", target)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    main()
