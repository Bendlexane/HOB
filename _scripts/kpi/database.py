#!/usr/bin/env python3
"""SQLite layer for research_kpis.db.

Handles schema creation (idempotent), inserts, and simple queries.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("kpi.database")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kpi_daily (
    date TEXT PRIMARY KEY,
    words_written INTEGER DEFAULT 0,
    words_added INTEGER DEFAULT 0,
    words_removed INTEGER DEFAULT 0,
    notes_created INTEGER DEFAULT 0,
    notes_modified INTEGER DEFAULT 0,
    papers_added_zotero INTEGER DEFAULT 0,
    papers_annotated_zotero INTEGER DEFAULT 0,
    obsidian_time_min INTEGER DEFAULT 0,
    teaching_time_min INTEGER DEFAULT 0,
    commits_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reading_by_topic (
    date TEXT,
    category TEXT,
    papers_read INTEGER DEFAULT 0,
    annotations_made INTEGER DEFAULT 0,
    PRIMARY KEY (date, category)
);

CREATE TABLE IF NOT EXISTS reading_depth (
    date TEXT PRIMARY KEY,
    annotations_total INTEGER DEFAULT 0,
    papers_with_annotations INTEGER DEFAULT 0,
    annotations_per_paper_avg REAL DEFAULT 0.0,
    papers_revisited INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS time_by_activity (
    date TEXT,
    category TEXT,
    project_code TEXT,
    minutes INTEGER DEFAULT 0,
    PRIMARY KEY (date, category, project_code)
);

CREATE TABLE IF NOT EXISTS work_pattern (
    date TEXT PRIMARY KEY,
    weekend_minutes INTEGER DEFAULT 0,
    late_night_minutes INTEGER DEFAULT 0,
    early_morning_minutes INTEGER DEFAULT 0,
    deep_work_blocks INTEGER DEFAULT 0,
    context_switches INTEGER DEFAULT 0,
    first_activity_time TEXT,
    last_activity_time TEXT,
    is_holiday INTEGER DEFAULT 0
);

-- Funding snapshot — written daily by funding_runway.py from 02_GRANTS/*/_grant.md
CREATE TABLE IF NOT EXISTS funding_status (
    date TEXT PRIMARY KEY,
    runway_months REAL DEFAULT 0.0,      -- coverage from active grants
    obtained_eur INTEGER DEFAULT 0,      -- sum of amount_funded (active) = money actually obtained
    pipeline_eur INTEGER DEFAULT 0,      -- sum of amount_requested (submitted, awaiting decision)
    grants_submitted_ytd INTEGER DEFAULT 0,
    grants_funded_ytd INTEGER DEFAULT 0,
    success_rate_5y REAL
);

-- Fit-score history — the RAG evaluator's score over time. The row frozen at
-- submission (snapshot_at_submit=1) is the baseline for a future P(win | score).
CREATE TABLE IF NOT EXISTS grant_fit_history (
    grant_code TEXT,
    date TEXT,
    overall REAL,
    excellence REAL,
    impact REAL,
    implementation REAL,
    snapshot_at_submit INTEGER DEFAULT 0,
    outcome TEXT,                        -- funded | rejected | withdrawn (set on resolution)
    PRIMARY KEY (grant_code, date)
);

CREATE VIEW IF NOT EXISTS editing_depth_daily AS
SELECT date,
       words_written AS words_added_net,
       words_added,
       words_removed,
       CAST(words_removed AS REAL) / NULLIF(words_added + words_removed, 0) AS depth
FROM kpi_daily;
"""


class KpiDb:
    """Thread-unsafe connection to research_kpis.db."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def ensure_schema(self) -> None:
        conn = self.connect()
        # Migration: ensure words_added and words_removed columns exist in kpi_daily
        try:
            cursor = conn.execute("PRAGMA table_info(kpi_daily)")
            columns = [r["name"] for r in cursor.fetchall()]
            if columns:
                if "words_added" not in columns:
                    conn.execute("ALTER TABLE kpi_daily ADD COLUMN words_added INTEGER DEFAULT 0")
                    logger.info("Migrated kpi_daily schema: added words_added column")
                if "words_removed" not in columns:
                    conn.execute("ALTER TABLE kpi_daily ADD COLUMN words_removed INTEGER DEFAULT 0")
                    logger.info("Migrated kpi_daily schema: added words_removed column")
        except sqlite3.OperationalError:
            pass

        conn.executescript(SCHEMA_SQL)
        conn.commit()
        logger.info("Schema ensured at %s", self.db_path)

    def upsert_kpi_daily(self, row: dict) -> None:
        conn = self.connect()
        # Fetch existing row to merge to avoid overwriting other metrics (e.g. Zotero vs Git)
        cursor = conn.execute("SELECT * FROM kpi_daily WHERE date = ?", (row["date"],))
        existing = cursor.fetchone()
        if existing:
            merged = {**dict(existing), **row}
        else:
            merged = {
                "date": row["date"],
                "words_written": 0,
                "words_added": 0,
                "words_removed": 0,
                "notes_created": 0,
                "notes_modified": 0,
                "papers_added_zotero": 0,
                "papers_annotated_zotero": 0,
                "obsidian_time_min": 0,
                "teaching_time_min": 0,
                "commits_count": 0,
                **row
            }

        conn.execute(
            """INSERT INTO kpi_daily (
                   date, words_written, words_added, words_removed,
                   notes_created, notes_modified, papers_added_zotero,
                   papers_annotated_zotero, obsidian_time_min,
                   teaching_time_min, commits_count
               ) VALUES (
                   :date, :words_written, :words_added, :words_removed,
                   :notes_created, :notes_modified, :papers_added_zotero,
                   :papers_annotated_zotero, :obsidian_time_min,
                   :teaching_time_min, :commits_count
               ) ON CONFLICT(date) DO UPDATE SET
                   words_written = excluded.words_written,
                   words_added = excluded.words_added,
                   words_removed = excluded.words_removed,
                   notes_created = excluded.notes_created,
                   notes_modified = excluded.notes_modified,
                   papers_added_zotero = excluded.papers_added_zotero,
                   papers_annotated_zotero = excluded.papers_annotated_zotero,
                   obsidian_time_min = excluded.obsidian_time_min,
                   teaching_time_min = excluded.teaching_time_min,
                   commits_count = excluded.commits_count""",
            merged,
        )
        conn.commit()

    def upsert_reading_by_topic(self, rows: list[dict]) -> None:
        conn = self.connect()
        conn.executemany(
            """INSERT INTO reading_by_topic (date, category, papers_read, annotations_made)
               VALUES (:date, :category, :papers_read, :annotations_made)
               ON CONFLICT(date, category) DO UPDATE SET
                   papers_read = excluded.papers_read,
                   annotations_made = excluded.annotations_made""",
            rows,
        )
        conn.commit()

    def upsert_reading_depth(self, row: dict) -> None:
        conn = self.connect()
        conn.execute(
            """INSERT INTO reading_depth (date, annotations_total, papers_with_annotations,
                                          annotations_per_paper_avg, papers_revisited)
               VALUES (:date, :annotations_total, :papers_with_annotations,
                       :annotations_per_paper_avg, :papers_revisited)
               ON CONFLICT(date) DO UPDATE SET
                   annotations_total = excluded.annotations_total,
                   papers_with_annotations = excluded.papers_with_annotations,
                   annotations_per_paper_avg = excluded.annotations_per_paper_avg,
                   papers_revisited = excluded.papers_revisited""",
            row,
        )
        conn.commit()

    def upsert_funding_status(self, row: dict) -> None:
        conn = self.connect()
        conn.execute(
            """INSERT INTO funding_status
                   (date, runway_months, obtained_eur, pipeline_eur,
                    grants_submitted_ytd, grants_funded_ytd, success_rate_5y)
               VALUES (:date, :runway_months, :obtained_eur, :pipeline_eur,
                       :grants_submitted_ytd, :grants_funded_ytd, :success_rate_5y)
               ON CONFLICT(date) DO UPDATE SET
                   runway_months = excluded.runway_months,
                   obtained_eur = excluded.obtained_eur,
                   pipeline_eur = excluded.pipeline_eur,
                   grants_submitted_ytd = excluded.grants_submitted_ytd,
                   grants_funded_ytd = excluded.grants_funded_ytd,
                   success_rate_5y = excluded.success_rate_5y""",
            row,
        )
        conn.commit()

    def record_grant_fit(self, grant_code: str, when: str, overall, excellence,
                         impact, implementation, snapshot_at_submit: int = 0) -> None:
        conn = self.connect()
        conn.execute(
            """INSERT INTO grant_fit_history
                   (grant_code, date, overall, excellence, impact, implementation, snapshot_at_submit)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(grant_code, date) DO UPDATE SET
                   overall=excluded.overall, excellence=excluded.excellence,
                   impact=excluded.impact, implementation=excluded.implementation,
                   snapshot_at_submit=MAX(grant_fit_history.snapshot_at_submit, excluded.snapshot_at_submit)""",
            (grant_code, when, overall, excellence, impact, implementation, snapshot_at_submit),
        )
        conn.commit()

    def set_grant_outcome(self, grant_code: str, outcome: str) -> None:
        """Record the funding outcome on the submission-baseline row(s)."""
        conn = self.connect()
        conn.execute(
            "UPDATE grant_fit_history SET outcome = ? WHERE grant_code = ? AND snapshot_at_submit = 1",
            (outcome, grant_code),
        )
        conn.commit()

    TABLES = (
        "kpi_daily",
        "reading_by_topic",
        "reading_depth",
        "time_by_activity",
        "work_pattern",
        "funding_status",
        "grant_fit_history",
    )

    def export_to_excel(
        self,
        out_dir: Path,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Path:
        """Export the KPI DB to an .xlsx workbook.

        Produces a 'Summary' sheet (period totals + reading-by-topic pivot)
        followed by one raw-dump sheet per table. Optional date_from/date_to
        (YYYY-MM-DD inclusive) filter every table on its `date` column.

        Returns the path of the written workbook.
        """
        import pandas as pd

        conn = self.connect()

        where = ""
        params: list[str] = []
        if date_from:
            where = " WHERE date >= ?"
            params.append(date_from)
        if date_to:
            where += " AND date <= ?" if where else " WHERE date <= ?"
            params.append(date_to)

        frames = {
            t: pd.read_sql_query(
                f"SELECT * FROM {t}{where} ORDER BY date", conn, params=params
            )
            for t in self.TABLES
        }

        daily = frames["kpi_daily"]
        depth = frames["reading_depth"]
        topic = frames["reading_by_topic"]

        def _sum(df: "pd.DataFrame", col: str) -> int:
            return int(df[col].sum()) if not df.empty else 0

        period_lo = date_from or (daily["date"].min() if not daily.empty else "—")
        period_hi = date_to or (daily["date"].max() if not daily.empty else "—")

        summary_df = pd.DataFrame(
            [
                ("Period", f"{period_lo} → {period_hi}"),
                ("Days with data", len(daily)),
                ("Papers added (Zotero)", _sum(daily, "papers_added_zotero")),
                ("Papers annotated (Zotero)", _sum(daily, "papers_annotated_zotero")),
                ("Annotations total", _sum(depth, "annotations_total")),
                ("Papers revisited", _sum(depth, "papers_revisited")),
                ("Words written", _sum(daily, "words_written")),
                ("Commits", _sum(daily, "commits_count")),
            ],
            columns=["Metric", "Value"],
        )

        if not topic.empty:
            topic_pivot = (
                topic.groupby("category", as_index=False)[
                    ["papers_read", "annotations_made"]
                ]
                .sum()
                .sort_values("papers_read", ascending=False)
            )
        else:
            topic_pivot = pd.DataFrame(
                columns=["category", "papers_read", "annotations_made"]
            )

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"kpis_{date.today().isoformat()}.xlsx"

        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            summary_df.to_excel(writer, sheet_name="Summary", index=False)
            label_row = len(summary_df) + 2
            ws = writer.sheets["Summary"]
            ws.cell(row=label_row, column=1, value="Reading by topic (totals)")
            topic_pivot.to_excel(
                writer, sheet_name="Summary", index=False, startrow=label_row
            )
            for name, df in frames.items():
                df.to_excel(writer, sheet_name=name[:31], index=False)

        logger.info("Exported %d tables to %s", len(frames), out_path)
        return out_path


def main(argv: Optional[list[str]] = None) -> None:
    # Ensure _scripts/ is importable for sibling utils.* imports
    scripts_dir = Path(__file__).resolve().parent.parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from utils.vault import VaultPaths

    parser = argparse.ArgumentParser(description="research_kpis.db utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    exp = sub.add_parser("export", help="Export the KPI DB to an .xlsx workbook")
    exp.add_argument("--from", dest="date_from", default=None, help="Start date YYYY-MM-DD (inclusive)")
    exp.add_argument("--to", dest="date_to", default=None, help="End date YYYY-MM-DD (inclusive)")
    exp.add_argument("-o", "--out-dir", default=None, help="Output directory (default: 06_PLANNING/kpis/exports/)")
    exp.add_argument("--db", default=None, help="Path to research_kpis.db (default: vault path)")

    args = parser.parse_args(argv)
    vault = VaultPaths()

    if args.command == "export":
        db_path = Path(args.db) if args.db else vault.kpi_db
        out_dir = Path(args.out_dir) if args.out_dir else vault.kpi_exports
        out_path = KpiDb(db_path).export_to_excel(out_dir, args.date_from, args.date_to)
        print(out_path)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    main()
