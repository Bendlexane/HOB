#!/usr/bin/env python3
"""Collect Zotero reading KPIs.

Queries Zotero SQLite (immutable=1) for:
  - papers_added_zotero: journal articles + preprints added on a target date
  - papers_annotated_zotero: distinct parent items with annotations created on target date
  - annotations_total: count of annotations created on target date
  - papers_revisited: attachments with lastRead on target date
  - reading_by_topic: for papers annotated on target date, classify via Ollama
    or from existing tags (if Zotero Actions & Tags plugin already tagged them)

Library-agnostic: queries all libraries (user + groups) by default.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("kpi.zotero_stats")

OLLAMA_TIMEOUT = 60

# ⚠️ SYSTEM FRAGILITY WARNING:
# The CATEGORIES list is duplicated between this Python script and
# the Zotero JS action script `_scripts/automation/clean_tags_zotero_library.js`.
# If you modify categories here, you MUST also update them there to prevent
# pipeline/KPI collection breakage.
CATEGORIES = frozenset({
    "phylogenomics",
    "taxonomy",
    "morphometry",
    "ecology_biogeography",
    "genetics",
    "cytogenetics",
    "stats_ml",
    "methods_software",
    "philosophy",
    "informatics",
    "other",
})


def _immutable_connect(zotero_db: Path) -> sqlite3.Connection:
    uri = f"file:{zotero_db.resolve()}?immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_tag_prompt(tag_prompt_path: Path) -> str:
    return tag_prompt_path.read_text().strip()


def _query_papers_added(conn: sqlite3.Connection, target: str) -> int:
    row = conn.execute(
        """SELECT COUNT(*) AS cnt FROM items
           WHERE itemTypeID IN (20, 38)
             AND date(dateAdded) = ?""",
        (target,),
    ).fetchone()
    return row["cnt"] if row else 0


def _query_papers_annotated(conn: sqlite3.Connection, target: str) -> int:
    row = conn.execute(
        """SELECT COUNT(DISTINCT att.parentItemID) AS cnt
           FROM itemAnnotations a
           JOIN itemAttachments att ON a.parentItemID = att.itemID
           JOIN items i ON a.itemID = i.itemID
           JOIN items parent ON att.parentItemID = parent.itemID
           WHERE date(i.dateAdded) = ?
             AND parent.itemTypeID IN (20, 38)""",
        (target,),
    ).fetchone()
    return row["cnt"] if row else 0


def _query_annotations_total(conn: sqlite3.Connection, target: str) -> int:
    row = conn.execute(
        """SELECT COUNT(*) AS cnt
           FROM itemAnnotations a
           JOIN items i ON a.itemID = i.itemID
           WHERE date(i.dateAdded) = ?""",
        (target,),
    ).fetchone()
    return row["cnt"] if row else 0


def _query_papers_revisited(conn: sqlite3.Connection, target: str) -> int:
    ts_start = int(date.fromisoformat(target).strftime("%s"))
    ts_end = ts_start + 86400
    row = conn.execute(
        """SELECT COUNT(*) AS cnt
           FROM itemAttachments att
           WHERE att.lastRead >= ? AND att.lastRead < ?
             AND att.parentItemID IN (
                 SELECT itemID FROM items WHERE itemTypeID IN (20, 38)
             )""",
        (ts_start, ts_end),
    ).fetchone()
    return row["cnt"] if row else 0


def _get_papers_with_annotations(
    conn: sqlite3.Connection, target: str
) -> list[dict]:
    """Return journal articles and preprints that received annotations on
    target date, with per-paper annotation count and metadata."""
    rows = conn.execute(
        """SELECT parent.itemID,
                  parent.key,
                  parent.libraryID,
                  COUNT(a.itemID) AS annotation_count
           FROM itemAnnotations a
           JOIN itemAttachments att ON a.parentItemID = att.itemID
           JOIN items ai ON a.itemID = ai.itemID
           JOIN items parent ON att.parentItemID = parent.itemID
           WHERE date(ai.dateAdded) = ?
             AND parent.itemTypeID IN (20, 38)
           GROUP BY parent.itemID, parent.key, parent.libraryID""",
        (target,),
    ).fetchall()

    results = []
    for r in rows:
        title = _get_item_title(conn, r["itemID"])
        abstract = _get_item_abstract(conn, r["itemID"])
        tags = _get_item_tags(conn, r["itemID"])
        library_label = _library_name(conn, r["libraryID"])
        results.append({
            "item_id": r["itemID"],
            "key": r["key"],
            "library": library_label,
            "title": title or "",
            "abstract": abstract or "",
            "tags": tags,
            "annotation_count": r["annotation_count"],
        })
    return results


def _get_item_title(conn: sqlite3.Connection, item_id: int) -> str:
    row = conn.execute(
        """SELECT idv.value AS title
           FROM itemData idat
           JOIN itemDataValues idv ON idat.valueID = idv.valueID
           WHERE idat.itemID = ? AND idat.fieldID = 1""",
        (item_id,),
    ).fetchone()
    return row["title"] if row else ""


def _get_item_abstract(conn: sqlite3.Connection, item_id: int) -> str:
    row = conn.execute(
        """SELECT idv.value AS abstract
           FROM itemData idat
           JOIN itemDataValues idv ON idat.valueID = idv.valueID
           WHERE idat.itemID = ? AND idat.fieldID = 90""",
        (item_id,),
    ).fetchone()
    return row["abstract"] if row else ""


def _get_item_tags(conn: sqlite3.Connection, item_id: int) -> list[str]:
    rows = conn.execute(
        """SELECT t.name FROM tags t
           JOIN itemTags it ON t.tagID = it.tagID
           WHERE it.itemID = ?
           ORDER BY t.name""",
        (item_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def _library_name(conn: sqlite3.Connection, library_id: int) -> str:
    if library_id == 1:
        return "My Library"
    row = conn.execute(
        "SELECT name FROM groups WHERE libraryID = ?", (library_id,)
    ).fetchone()
    return row["name"] if row else f"Library {library_id}"


def _parse_ollama_response(raw: str) -> Optional[str]:
    """Extract category from Ollama's response, stripping markdown if present."""
    text = raw.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0] if "```" in text else text
    text = text.strip()
    try:
        parsed = json.loads(text)
        return parsed.get("category")
    except json.JSONDecodeError:
        m = __import__("re").search(r'"category"\s*:\s*"([^"]+)"', text)
        return m.group(1) if m else None


def classify_via_ollama(
    title: str,
    abstract: str,
    keywords: list[str],
    prompt_template: str,
    ollama_host: str = "http://localhost:11434",
    model: str = "gemma4:latest",
) -> str:
    """Send paper metadata to Ollama and return a category tag.

    Returns 'other' on any error or invalid response.
    """
    tag_str = ", ".join(keywords) if keywords else ""
    prompt = prompt_template.replace("{title}", title or "")
    prompt = prompt.replace("{abstract}", (abstract or "")[:2000])
    prompt = prompt.replace("{keywords}", tag_str)

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }).encode()

    try:
        req = urllib.request.Request(
            f"{ollama_host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            body = json.loads(resp.read().decode())

        raw = body.get("response", "").strip()
        category = _parse_ollama_response(raw)
        if category and category in CATEGORIES:
            return category
        if category:
            logger.warning("Ollama returned unknown category: %s", category)
        return "other"
    except Exception as exc:
        logger.warning("Ollama classification failed for '%s': %s", title[:60], exc)
        return "other"


def check_existing_tag(tags: list[str]) -> Optional[str]:
    """If paper already has a category tag from Actions & Tags plugin, return it."""
    for t in tags:
        if t in CATEGORIES:
            return t
    return None


def collect(
    zotero_db: Path,
    tag_prompt_path: Path,
    target: Optional[str] = None,
    ollama_host: str = "http://localhost:11434",
    ollama_model: str = "gemma4:latest",
) -> dict:
    """Collect all Zotero KPIs for a target date (default: yesterday).

    Returns a dict with:
      - papers_added, papers_annotated, annotations_total, papers_revisited
      - topics: list of {category, papers_read, annotations_made}
      - reading_depth: {annotations_total, papers_with_annotations, papers_revisited}
    """
    if target is None:
        target = (date.today() - timedelta(days=1)).isoformat()

    conn = _immutable_connect(zotero_db)
    prompt_template = load_tag_prompt(tag_prompt_path)

    papers_added = _query_papers_added(conn, target)
    papers_annotated = _query_papers_annotated(conn, target)
    annotations_total = _query_annotations_total(conn, target)
    papers_revisited = _query_papers_revisited(conn, target)

    annotated_papers = _get_papers_with_annotations(conn, target)

    topic_data: dict[str, dict] = {}  # {category: {"papers": int, "annotations": int}}
    for paper in annotated_papers:
        existing_tag = check_existing_tag(paper["tags"])
        if existing_tag:
            cat = existing_tag
        else:
            cat = classify_via_ollama(
                paper["title"],
                paper["abstract"],
                paper["tags"],
                prompt_template,
                ollama_host,
                ollama_model,
            )
        if cat not in topic_data:
            topic_data[cat] = {"papers": 0, "annotations": 0}
        topic_data[cat]["papers"] += 1
        topic_data[cat]["annotations"] += paper["annotation_count"]

    topics = [
        {
            "date": target,
            "category": cat,
            "papers_read": d["papers"],
            "annotations_made": d["annotations"],
        }
        for cat, d in sorted(topic_data.items())
    ]

    papers_with_annotations_count = len(annotated_papers)
    avg_annotations = (
        round(annotations_total / papers_with_annotations_count, 1)
        if papers_with_annotations_count > 0
        else 0.0
    )

    result = {
        "date": target,
        "papers_added": papers_added,
        "papers_annotated": papers_annotated,
        "annotations_total": annotations_total,
        "papers_revisited": papers_revisited,
        "topics": topics,
        "reading_depth": {
            "annotations_total": annotations_total,
            "papers_with_annotations": papers_with_annotations_count,
            "annotations_per_paper_avg": avg_annotations,
            "papers_revisited": papers_revisited,
        },
    }

    conn.close()
    return result


if __name__ == "__main__":
    import sys
    from utils.config import load as load_config

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    cfg = load_config()
    zotero_db = Path(cfg.get("ZOTERO_DB"))
    script_dir = Path(__file__).resolve().parent
    tag_prompt = script_dir / "tag_prompt.txt"
    ollama_host = cfg.get("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = cfg.get("OLLAMA_MODEL", "gemma4:latest")

    result = collect(zotero_db, tag_prompt, ollama_host=ollama_host, ollama_model=ollama_model)
    print(json.dumps(result, indent=2))
