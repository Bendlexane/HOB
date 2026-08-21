#!/usr/bin/env python3
"""literature.py — single source of truth for literature-note identity.

Every literature note in 03_KNOWLEDGE/literature/ — no matter which pipeline
produced it (Templater `literature-note.md`, `pdf_to_md.py`, or
`staging_processor.py`) — must satisfy `_scripts/ops/schemas/literature.schema.yaml`:

    required: [type, citekey, stage]
    citekey:  ^[a-z0-9_-]+$        (== filename stem)
    stage:    seed|litnote|zettel|claim|manuscript-fragment   (import default: litnote)
    status:   unread|reading|annotated|synthesized

This module centralises citekey sanitisation and canonical frontmatter
generation so the three producers cannot drift again (see Audit C4/C5).
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from typing import Iterable, Optional

# Valid characters for a citekey / filename stem, per literature.schema.yaml
_CITEKEY_RE = re.compile(r"^[a-z0-9_-]+$")
_NONWORD_RE = re.compile(r"[^a-z0-9]+")


def slugify_citekey(raw: str) -> str:
    """Coerce any string into a schema-valid citekey (^[a-z0-9_-]+$).

    "Johnson et al. - 2019 - A Universal Probe Set…" -> "johnson_et_al_2019_a_universal_probe_set"
    Better BibTeX citekeys ("johnson2019universal") pass through unchanged.
    """
    s = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = _NONWORD_RE.sub("_", s)        # any run of non-word chars -> single _
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "untitled"


def is_valid_citekey(value: str) -> bool:
    return bool(_CITEKEY_RE.match(value))


def _yaml_list(items: Optional[Iterable[str]]) -> str:
    items = [i for i in (items or []) if i]
    if not items:
        return "[]"
    inner = ", ".join(f'"{i}"' for i in items)
    return f"[{inner}]"


def build_frontmatter(
    citekey: str,
    *,
    stage: str = "litnote",
    status: str = "unread",
    authors: Optional[Iterable[str]] = None,
    year: Optional[int] = None,
    journal: str = "",
    doi: str = "",
    project_code: Optional[Iterable[str]] = None,
    tags: Optional[Iterable[str]] = None,
    source: str = "",            # provenance: zotero | pdf-ocr | staging | manual
    source_pdf: str = "",        # provenance (OCR only)
    ocr_backend: str = "",       # provenance (OCR only)
    pages: Optional[int] = None, # provenance (OCR only)
    title: str = "",
) -> str:
    """Return canonical literature-note YAML frontmatter (schema-conformant).

    The required schema core (type, citekey, stage) is always present; status
    and bibliographic fields are always emitted as keys so the note is ready to
    fill. Provenance fields are only written when supplied.
    """
    citekey = slugify_citekey(citekey)
    today = datetime.date.today().isoformat()

    lines = [
        "---",
        "type: literature",
        f"citekey: {citekey}",
        f"stage: {stage}",
        f"status: {status}",
    ]
    if title:
        # Quote to survive colons in paper titles.
        safe = title.replace('"', "'")
        lines.append(f'title: "{safe}"')
    lines += [
        f"authors: {_yaml_list(authors)}",
        f"year: {year if year is not None else ''}",
        f"journal: {journal}",
        f"doi: {doi}",
        f"project_code: {_yaml_list(project_code)}",
        f"tags: {_yaml_list(tags)}",
    ]
    # Provenance block — optional, never required by the schema.
    if source:
        lines.append(f"source: {source}")
    if source_pdf:
        lines.append(f'source_pdf: "{source_pdf}"')
    if ocr_backend:
        lines.append(f"ocr_backend: {ocr_backend}")
    if pages is not None:
        lines.append(f"pages: {pages}")
    lines.append(f"date_imported: {today}")
    lines.append("---")
    return "\n".join(lines) + "\n"
