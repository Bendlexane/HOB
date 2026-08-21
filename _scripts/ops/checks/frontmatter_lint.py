#!/usr/bin/env python3
"""frontmatter_lint.py — validate note frontmatter against ops/schemas/*.

Catches the silent failures that corrupt Dataview/Bases queries: a typo in an
enum (`role: coautor`), a malformed citekey, a broken YAML block. Such a note
does not error anywhere — it just silently drops out of every query that filters
on the bad field. This check surfaces it.

Mapping note → schema:
  * by `type:` field          literature|concept|idea|lab-note|protocol|grant
  * by filename (no `type:`)   _project.md → project, _grant.md → grant
  * anything else              skipped (most notes legitimately have no schema)

Severity:
  🔴 red     a note that SHOULD validate fails (enum/pattern/required violation)
  🟡 yellow  frontmatter present but YAML cannot be parsed
  ℹ️ info    summary counts

Usage:
    python3 frontmatter_lint.py            # human-readable
    python3 frontmatter_lint.py --json     # machine-readable findings
    python3 frontmatter_lint.py --verbose  # also list every clean/skipped file
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("❌ pyyaml not installed: pip install pyyaml")
try:
    from jsonschema import Draft7Validator
except ImportError:
    sys.exit("❌ jsonschema not installed: pip install jsonschema")

OPS_DIR = Path(__file__).resolve().parent.parent          # _scripts/ops
SCHEMA_DIR = OPS_DIR / "schemas"
VAULT_ROOT = OPS_DIR.parent.parent                         # repo root

# Directories never linted (plugin output, system, binaries, vcs).
SKIP_DIRS = {
    ".git", ".obsidian", ".trash", ".space", ".makemd", ".agents", ".claude",
    "wiki", "_scripts", "__pycache__", "node_modules", ".venv",
}

# type: <value>  →  schema filename
TYPE_SCHEMA = {
    "literature": "literature.schema.yaml",
    "concept": "concept.schema.yaml",
    "idea": "idea.schema.yaml",
    "lab-note": "lab-note.schema.yaml",
    "protocol": "protocol.schema.yaml",
    "grant": "_grant.schema.yaml",
}
# filename  →  schema filename  (for notes that carry no `type:` field)
FILENAME_SCHEMA = {
    "_project.md": "_project.schema.yaml",
    "_grant.md": "_grant.schema.yaml",
}

_validators: dict[str, Draft7Validator] = {}


def _validator(schema_file: str) -> Draft7Validator:
    if schema_file not in _validators:
        schema = yaml.safe_load((SCHEMA_DIR / schema_file).read_text(encoding="utf-8"))
        _validators[schema_file] = Draft7Validator(schema)
    return _validators[schema_file]


def _normalize(obj):
    """Coerce YAML-native dates to ISO strings so `format: date` (type: string) validates.

    PyYAML parses `created: 2025-09-01` into a datetime.date; JSON Schema's
    `type: string` would (correctly, by its own rules) reject it. The value is
    semantically a valid date string, so we stringify before validating.
    """
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    return obj


def _parse_frontmatter(text: str) -> tuple[dict | None, str | None]:
    """Return (frontmatter_dict, error). (None, None) means: no frontmatter block."""
    if not text.startswith("---"):
        return None, None
    # Frontmatter is the block between the first '---' and the next line '---'.
    end = text.find("\n---", 3)
    if end == -1:
        return None, "opening '---' but no closing '---'"
    block = text[3:end].lstrip("\n")
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {str(e).splitlines()[0]}"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return None, "frontmatter is not a mapping"
    return _normalize(data), None


def _schema_for(path: Path, fm: dict) -> str | None:
    """Pick the schema for a note. Explicit `type:` always wins over filename.

    A note that declares `type:` we don't have a schema for (peer-review, meta,
    reference, course, …) is intentionally skipped — it is NOT a project just
    because it is named _project.md (peer-review hubs reuse that filename).
    Only an untyped note falls back to the filename mapping.
    """
    t = fm.get("type")
    if isinstance(t, str):
        return TYPE_SCHEMA.get(t)            # None → no schema for this type → skip
    return FILENAME_SCHEMA.get(path.name)    # untyped hub note (_project.md / _grant.md)


def _iter_notes():
    for p in VAULT_ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in p.relative_to(VAULT_ROOT).parts):
            continue
        yield p


def run() -> list[dict]:
    findings: list[dict] = []
    n_checked = n_clean = n_skipped = 0

    for path in _iter_notes():
        rel = str(path.relative_to(VAULT_ROOT))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            findings.append({"severity": "yellow", "check": "frontmatter_lint",
                             "target": rel, "message": f"cannot read file: {e}"})
            continue

        fm, parse_err = _parse_frontmatter(text)
        if parse_err is not None:
            findings.append({"severity": "yellow", "check": "frontmatter_lint",
                             "target": rel, "message": parse_err})
            continue
        if fm is None:
            n_skipped += 1
            continue

        schema_file = _schema_for(path, fm)
        if schema_file is None:
            n_skipped += 1
            continue

        n_checked += 1
        errors = sorted(_validator(schema_file).iter_errors(fm), key=lambda e: list(e.path))
        if not errors:
            n_clean += 1
            continue
        for err in errors:
            loc = ".".join(str(x) for x in err.path) or "(root)"
            findings.append({
                "severity": "red", "check": "frontmatter_lint", "target": rel,
                "message": f"[{schema_file.replace('.schema.yaml', '')}] {loc}: {err.message}",
            })

    findings.append({
        "severity": "info", "check": "frontmatter_lint", "target": "summary",
        "message": f"{n_checked} validated, {n_clean} clean, "
                   f"{n_checked - n_clean} with errors, {n_skipped} skipped (no schema)",
    })
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate note frontmatter against schemas")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="(reserved) list clean files too")
    args = ap.parse_args()

    findings = run()
    if args.json:
        print(json.dumps(findings, indent=2, ensure_ascii=False))
        return 0

    icon = {"red": "🔴", "yellow": "🟡", "info": "ℹ️", "ok": "✅"}
    order = ["red", "yellow", "info", "ok"]
    for f in sorted(findings, key=lambda x: order.index(x["severity"])):
        print(f"{icon.get(f['severity'], '?')} {f['target']}: {f['message']}")
    return 1 if any(f["severity"] == "red" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
