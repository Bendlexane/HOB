#!/usr/bin/env python3
"""JSON exporter for research_kpis.db.

Queries the SQLite tables and outputs a clean JSON file to be consumed by
the Obsidian home note dashboard.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger("kpi.export_json")

# Ensure _scripts/ is on the path
_SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from utils.vault import VaultPaths


def export_kpi_to_json(db_path: Path, out_path: Path) -> None:
    """Read research_kpis.db and write kpi_data.json."""
    if not db_path.exists():
        logger.error("DB file not found at %s", db_path)
        return

    logger.info("Connecting to SQLite at %s", db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Fetch last 30 days of daily metrics joined with reading depth
    logger.info("Fetching daily metrics")
    cur.execute(
        """
        SELECT 
            kd.date,
            kd.words_written,
            kd.notes_created,
            kd.notes_modified,
            kd.papers_added_zotero,
            kd.papers_annotated_zotero,
            kd.obsidian_time_min,
            kd.teaching_time_min,
            kd.commits_count,
            COALESCE(rd.annotations_total, 0) as annotations_total,
            COALESCE(rd.papers_with_annotations, 0) as papers_with_annotations,
            COALESCE(rd.annotations_per_paper_avg, 0.0) as annotations_per_paper_avg,
            COALESCE(rd.papers_revisited, 0) as papers_revisited
        FROM kpi_daily kd
        LEFT JOIN reading_depth rd ON kd.date = rd.date
        ORDER BY kd.date DESC
        LIMIT 30
        """
    )
    daily_rows = [dict(row) for row in cur.fetchall()]
    # Reverse to chronological order for charts/sparklines
    daily_rows.reverse()

    # 2. Fetch aggregated reading by topic (totals)
    logger.info("Fetching topic stats")
    cur.execute(
        """
        SELECT category, SUM(papers_read) as papers_read, SUM(annotations_made) as annotations_made
        FROM reading_by_topic
        GROUP BY category
        ORDER BY papers_read DESC
        """
    )
    topic_rows = [dict(row) for row in cur.fetchall()]

    # 3. Calculate summary metrics (totals of all loaded data)
    logger.info("Computing summaries")
    cur.execute(
        """
        SELECT 
            MIN(date) as date_min,
            MAX(date) as date_max,
            SUM(words_written) as total_words_written,
            SUM(notes_created) as total_notes_created,
            SUM(notes_modified) as total_notes_modified,
            SUM(papers_added_zotero) as total_papers_added,
            SUM(papers_annotated_zotero) as total_papers_annotated,
            SUM(commits_count) as total_commits
        FROM kpi_daily
        """
    )
    kpi_summary = dict(cur.fetchone() or {})

    cur.execute(
        """
        SELECT 
            SUM(annotations_total) as total_annotations,
            SUM(papers_revisited) as total_papers_revisited
        FROM reading_depth
        """
    )
    depth_summary = dict(cur.fetchone() or {})

    summary = {
        "date_min": kpi_summary.get("date_min") or "—",
        "date_max": kpi_summary.get("date_max") or "—",
        "total_words_written": int(kpi_summary.get("total_words_written") or 0),
        "total_notes_created": int(kpi_summary.get("total_notes_created") or 0),
        "total_notes_modified": int(kpi_summary.get("total_notes_modified") or 0),
        "total_papers_added": int(kpi_summary.get("total_papers_added") or 0),
        "total_papers_annotated": int(kpi_summary.get("total_papers_annotated") or 0),
        "total_commits": int(kpi_summary.get("total_commits") or 0),
        "total_annotations": int(depth_summary.get("total_annotations") or 0),
        "total_papers_revisited": int(depth_summary.get("total_papers_revisited") or 0),
    }

    # 4. Construct final JSON payload
    data: dict[str, Any] = {
        "generated_at": date.today().isoformat(),
        "summary": summary,
        "daily": daily_rows,
        "topics": topic_rows,
    }

    # Write output file
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    
    logger.info("JSON KPI data exported to %s", out_path)
    conn.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    vault = VaultPaths()
    db_path = vault.kpi_db
    out_path = vault.kpi_db.parent / "kpi_data.json"
    export_kpi_to_json(db_path, out_path)


if __name__ == "__main__":
    main()
