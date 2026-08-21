#!/usr/bin/env python3
"""Export Zotero highlights and notes to Markdown or JSON.

Queries Zotero SQLite (immutable=1) and collects:
  - type 1 annotations: highlights (field ``text`` contains the selected text)
  - type 2 annotations: sticky notes (field ``comment`` contains the note body)
  - type 5 (area/image selections): skipped — no extractable text

Output is grouped by paper, sorted by page and position within each paper.
Highlights are further grouped by color with a human-readable label.

Usage
-----
# Today's annotations → stdout (Markdown)
python3 _scripts/kpi/zotero_highlights.py

# Specific date → file
python3 _scripts/kpi/zotero_highlights.py --date 2026-06-03 -o highlights.md

# Date range
python3 _scripts/kpi/zotero_highlights.py --from 2026-05-01 --to 2026-06-03 -o may_highlights.md

# Single paper by Zotero key
python3 _scripts/kpi/zotero_highlights.py --key ABC12345 -o paper_notes.md

# Filter by color label (comma-separated; see COLOR_MAP below)
python3 _scripts/kpi/zotero_highlights.py --date 2026-06-03 --colors red,yellow

# JSON output
python3 _scripts/kpi/zotero_highlights.py --date 2026-06-03 --format json
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("kpi.zotero_highlights")

# ---------------------------------------------------------------------------
# Color → human label mapping
# Zotero's built-in palette + common custom colours.
# Anything not listed falls back to the hex string.
# ---------------------------------------------------------------------------
COLOR_MAP: dict[str, str] = {
    # Reds / important
    "#ec2814": "red",
    "#ff6666": "red",
    "#fb5c89": "pink",
    "#f5a7af": "pink",
    # Yellows / general
    "#ffd400": "yellow",
    "#facd5a": "yellow",
    "#ffed99": "yellow",
    "#ffd100": "yellow",
    "#ffeb6b": "yellow",
    "#ffff00": "yellow",
    "#fffd2e": "yellow",
    "#ffe79d": "yellow",
    # Greens / follow-up
    "#7cc868": "green",
    "#5fb236": "green",
    "#c3f0a9": "green",
    "#9bd0a4": "green",
    # Blues / notes
    "#2ea8e5": "blue",
    "#69b0f1": "blue",
    "#aff5ff": "blue",
    # Purples / definitions
    "#a28ae5": "purple",
    "#9999ff": "purple",
    "#c885da": "purple",
    "#e56eee": "purple",
    # Oranges
    "#f19837": "orange",
    # Grey
    "#aaaaaa": "grey",
    "#e8fdc7": "green",
    "#fefbce": "yellow",
}

COLOR_EMOJI: dict[str, str] = {
    "red":    "🔴",
    "pink":   "🩷",
    "yellow": "🟡",
    "green":  "🟢",
    "blue":   "🔵",
    "purple": "🟣",
    "orange": "🟠",
    "grey":   "⚫",
}

# Annotation types
TYPE_HIGHLIGHT = 1
TYPE_NOTE = 2


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _immutable_connect(zotero_db: Path) -> sqlite3.Connection:
    uri = f"file:{zotero_db.resolve()}?immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _color_label(hex_color: Optional[str]) -> str:
    if not hex_color:
        return "other"
    return COLOR_MAP.get(hex_color.lower(), hex_color.lower())


# ---------------------------------------------------------------------------
# Core query
# ---------------------------------------------------------------------------

def _build_where(
    target_date: Optional[str],
    from_date: Optional[str],
    to_date: Optional[str],
    paper_key: Optional[str],
    color_labels: Optional[list[str]],
) -> tuple[str, list]:
    """Build the WHERE clause and parameter list for the main annotation query."""
    clauses: list[str] = ["ia.type IN (?, ?)"]
    params: list = [TYPE_HIGHLIGHT, TYPE_NOTE]

    if target_date:
        clauses.append("date(ai.dateAdded) = ?")
        params.append(target_date)
    elif from_date or to_date:
        if from_date:
            clauses.append("date(ai.dateAdded) >= ?")
            params.append(from_date)
        if to_date:
            clauses.append("date(ai.dateAdded) <= ?")
            params.append(to_date)

    if paper_key:
        clauses.append("parent.key = ?")
        params.append(paper_key)

    if color_labels:
        # Expand label → set of hex codes
        wanted_hex = {
            hx for hx, lbl in COLOR_MAP.items() if lbl in color_labels
        }
        # Also allow unknown labels passed directly as hex
        for lbl in color_labels:
            if lbl.startswith("#"):
                wanted_hex.add(lbl.lower())
        if wanted_hex:
            placeholders = ",".join("?" * len(wanted_hex))
            clauses.append(f"LOWER(COALESCE(ia.color,'')) IN ({placeholders})")
            params.extend(wanted_hex)

    return " AND ".join(clauses), params


def collect(
    zotero_db: Path,
    target_date: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    paper_key: Optional[str] = None,
    color_labels: Optional[list[str]] = None,
) -> list[dict]:
    """Return a list of paper dicts, each with their highlights.

    Each paper dict:
        key, title, authors, year, doi, library,
        highlights: list of {
            annotation_id, type, color, color_label, page,
            text, comment, date_added, sort_index
        }
    """
    conn = _immutable_connect(zotero_db)
    where, params = _build_where(
        target_date, from_date, to_date, paper_key, color_labels
    )

    rows = conn.execute(
        f"""
        SELECT
            ia.itemID          AS annotation_id,
            ia.type            AS ann_type,
            ia.text            AS highlighted_text,
            ia.comment         AS note_text,
            ia.color           AS color,
            ia.pageLabel       AS page_label,
            ia.sortIndex       AS sort_index,
            ai.dateAdded       AS date_added,
            parent.itemID      AS parent_id,
            parent.key         AS parent_key,
            parent.libraryID   AS library_id
        FROM itemAnnotations ia
        JOIN items ai     ON ia.itemID        = ai.itemID
        JOIN itemAttachments att ON ia.parentItemID = att.itemID
        JOIN items parent ON att.parentItemID = parent.itemID
        WHERE {where}
        ORDER BY parent.itemID, ia.sortIndex
        """,
        params,
    ).fetchall()

    if not rows:
        conn.close()
        return []

    # Collect unique parent IDs
    parent_ids = list({r["parent_id"] for r in rows})

    # Fetch metadata for all parents in one pass
    meta: dict[int, dict] = {}
    for pid in parent_ids:
        meta[pid] = _paper_meta(conn, pid)

    conn.close()

    # Group annotations by parent
    papers: dict[int, dict] = {}
    for r in rows:
        pid = r["parent_id"]
        if pid not in papers:
            papers[pid] = {
                **meta[pid],
                "highlights": [],
            }
        papers[pid]["highlights"].append({
            "annotation_id": r["annotation_id"],
            "type": r["ann_type"],
            "color": r["color"] or "",
            "color_label": _color_label(r["color"]),
            "page": r["page_label"] or "",
            "text": (r["highlighted_text"] or "").strip(),
            "comment": (r["note_text"] or "").strip(),
            "date_added": r["date_added"],
            "sort_index": r["sort_index"],
        })

    return list(papers.values())


def _paper_meta(conn: sqlite3.Connection, item_id: int) -> dict:
    """Fetch title, year, DOI, authors, key for a parent item."""
    key_row = conn.execute(
        "SELECT key, libraryID FROM items WHERE itemID = ?", (item_id,)
    ).fetchone()

    def _field(field_id: int) -> str:
        r = conn.execute(
            """SELECT idv.value FROM itemData idat
               JOIN itemDataValues idv ON idat.valueID = idv.valueID
               WHERE idat.itemID = ? AND idat.fieldID = ?""",
            (item_id, field_id),
        ).fetchone()
        return r[0] if r else ""

    title = _field(1)
    raw_date = _field(6)   # e.g. "2003" or "2003-01-01"
    doi = _field(58)
    year = raw_date[:4] if raw_date else ""

    authors = conn.execute(
        """SELECT c.lastName, c.firstName, ic.orderIndex
           FROM itemCreators ic
           JOIN creators c ON ic.creatorID = c.creatorID
           WHERE ic.itemID = ?
           ORDER BY ic.orderIndex""",
        (item_id,),
    ).fetchall()

    author_list = [
        f"{r['lastName']}, {r['firstName']}".strip(", ") for r in authors
    ]

    library_id = key_row["libraryID"] if key_row else 1
    library_row = conn.execute(
        "SELECT name FROM groups WHERE libraryID = ?", (library_id,)
    ).fetchone()
    library = library_row["name"] if library_row else "My Library"

    return {
        "item_id": item_id,
        "key": key_row["key"] if key_row else "",
        "title": title,
        "authors": author_list,
        "year": year,
        "doi": doi,
        "library": library,
    }


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _author_short(authors: list[str]) -> str:
    """'Last et al.' or 'Last & Last2' or 'Last'."""
    if not authors:
        return "Unknown"
    lasts = [a.split(",")[0].strip() for a in authors]
    if len(lasts) == 1:
        return lasts[0]
    if len(lasts) == 2:
        return f"{lasts[0]} & {lasts[1]}"
    return f"{lasts[0]} et al."


def to_markdown(papers: list[dict], title: str = "Zotero Highlights") -> str:
    lines: list[str] = [f"# {title}", ""]

    if not papers:
        lines.append("*No highlights found for the selected filters.*")
        return "\n".join(lines)

    for paper in papers:
        author_str = _author_short(paper["authors"])
        year = paper["year"]
        doi_str = f" · DOI: {paper['doi']}" if paper["doi"] else ""
        header = f"## {paper['title']}"
        lines.append(header)
        meta_line = f"**{author_str}** ({year}){doi_str} · `{paper['key']}`"
        lines.append(meta_line)
        lines.append("")

        # Group by color_label, preserving document order within each group
        groups: dict[str, list[dict]] = {}
        for h in paper["highlights"]:
            lbl = h["color_label"]
            groups.setdefault(lbl, []).append(h)

        for lbl, highlights in groups.items():
            emoji = COLOR_EMOJI.get(lbl, "◆")
            lines.append(f"### {emoji} {lbl.capitalize()}")
            for h in highlights:
                page = f"p. {h['page']}" if h["page"] else ""
                if h["type"] == TYPE_NOTE:
                    # Sticky note: body is in comment
                    body = h["comment"] or h["text"] or "*(empty note)*"
                    entry = f"- **[Note{', ' + page if page else ''}]** {body}"
                else:
                    text = h["text"] or "*(no text)*"
                    entry = f"- **[{page}]** “{text}”"
                    if h["comment"]:
                        entry += f"\n  > _{h['comment']}_"
                lines.append(entry)
            lines.append("")

    return "\n".join(lines)


def to_json(papers: list[dict]) -> str:
    return json.dumps(papers, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Zotero highlights to Markdown or JSON."
    )
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Export highlights added on this date (default: today).",
    )
    date_group.add_argument(
        "--from",
        dest="from_date",
        metavar="YYYY-MM-DD",
        help="Start of date range.",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        metavar="YYYY-MM-DD",
        help="End of date range (used with --from; default: today).",
    )
    parser.add_argument(
        "--key",
        metavar="ZOTERO_KEY",
        help="Export all highlights for a specific Zotero item key (ignores date filters).",
    )
    parser.add_argument(
        "--colors",
        metavar="LABEL[,LABEL...]",
        help=(
            "Comma-separated color labels to include. "
            "Labels: red, yellow, green, blue, purple, orange, pink, grey. "
            "Example: --colors red,yellow"
        ),
    )
    parser.add_argument(
        "--format",
        choices=["md", "json"],
        default="md",
        help="Output format: md (default) or json.",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="Write output to FILE instead of stdout.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export ALL highlights in the library (no date filter). Use with caution.",
    )
    return parser.parse_args(argv)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    args = _parse_args()

    # Resolve Zotero DB path from config
    _script_dir = Path(__file__).resolve().parent.parent
    if str(_script_dir) not in sys.path:
        sys.path.insert(0, str(_script_dir))
    from utils.config import load as load_config

    cfg = load_config()
    zotero_db = Path(cfg["ZOTERO_DB"])

    # Resolve date parameters
    target_date: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None

    if args.key:
        # Key mode: ignore all date filters
        pass
    elif args.all:
        pass  # no date filter
    elif args.from_date:
        from_date = args.from_date
        to_date = args.to_date or date.today().isoformat()
    else:
        target_date = args.date or date.today().isoformat()

    color_labels: Optional[list[str]] = None
    if args.colors:
        color_labels = [c.strip().lower() for c in args.colors.split(",")]

    papers = collect(
        zotero_db=zotero_db,
        target_date=target_date,
        from_date=from_date,
        to_date=to_date,
        paper_key=args.key,
        color_labels=color_labels,
    )

    # Build title for Markdown header
    if args.key:
        md_title = f"Highlights — {args.key}"
    elif args.all:
        md_title = "All Zotero Highlights"
    elif from_date:
        md_title = f"Highlights {from_date} → {to_date}"
    else:
        md_title = f"Highlights — {target_date}"

    if args.format == "json":
        output = to_json(papers)
    else:
        output = to_markdown(papers, title=md_title)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        total = sum(len(p["highlights"]) for p in papers)
        logger.info(
            "Exported %d highlight(s) from %d paper(s) → %s",
            total, len(papers), out_path,
        )
    else:
        print(output)


if __name__ == "__main__":
    main()
