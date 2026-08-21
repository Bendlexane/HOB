#!/usr/bin/env python3.10
"""Wiki linter for the Research vault.

Two scopes, two behaviors:

  - wiki/  (plugin-generated AI layer) → AUTO-DELETE polluted pages
  - 03_KNOWLEDGE/  (hand-authored)     → REPORT-ONLY (orphans, broken links, conflicts)

Run:
    python3 _scripts/automation/wiki_lint.py [--vault-root PATH] [--dry-run]

The report is saved to _scripts/ops/logs/YYYY-MM-DD-lint.md with `cssclasses: [graph-hide]`
so it stays accessible but invisible in the graph.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KNOWLEDGE_DIR = "03_KNOWLEDGE"
WIKI_DIR = "wiki"
LINT_OUT_DIR = "_scripts/ops/logs"

IMAGE_EXT_RE = re.compile(r".*\.(jpe?g|png|gif|pdf|svg|webp|bmp|tiff?)$", re.IGNORECASE)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
NAME_RE = re.compile(r'^name:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)
SOURCE_COUNT_RE = re.compile(r'^source-count:\s*(\d+)\s*$', re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_frontmatter(path: Path) -> dict[str, str]:
    """Parse YAML-like frontmatter into a flat dict of string values."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def read_body(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return FRONTMATTER_RE.sub("", text, count=1)


def iter_md(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return (p for p in root.rglob("*.md") if p.is_file())


def link_targets(text: str) -> list[str]:
    return [m.group(1).strip() for m in WIKILINK_RE.finditer(text)]


def is_image_node(name: str) -> bool:
    return bool(IMAGE_EXT_RE.match(name))


# ---------------------------------------------------------------------------
# wiki/ auto-clean
# ---------------------------------------------------------------------------

def clean_wiki_tree(wiki_root: Path, dry_run: bool) -> dict[str, list[str]]:
    """Auto-delete polluted pages in wiki/.

    Returns a dict grouping deletions by reason.
    """
    deleted: dict[str, list[str]] = defaultdict(list)
    if not wiki_root.exists():
        return deleted

    for md in iter_md(wiki_root):
        rel = str(md.relative_to(wiki_root.parent))
        basename = md.stem
        fm = read_frontmatter(md)
        body = read_body(md).strip()
        name = fm.get("name", basename)

        # 1. image-path artifact
        if is_image_node(name) or is_image_node(basename):
            deleted["image_artifact"].append(rel)
            if not dry_run:
                md.unlink()
            continue

        # 2. empty entity/concept (no facts, no definition, 0 sources)
        try:
            source_count = int(fm.get("source-count", "0"))
        except ValueError:
            source_count = 0
        has_content = bool(body) and not re.fullmatch(r"#+\s*\w[\w\s]*", body.split("\n", 1)[0])
        if source_count == 0 and not has_content:
            deleted["empty_node"].append(rel)
            if not dry_run:
                md.unlink()
            continue

        # 3. meta-file leaked (starts with _ or matches known meta patterns)
        if basename.startswith("_"):
            deleted["meta_file_leak"].append(rel)
            if not dry_run:
                md.unlink()
            continue

        # 4. path-fragment name (extraction of a path-like token)
        if "/" in name or name.startswith("."):
            deleted["path_fragment_name"].append(rel)
            if not dry_run:
                md.unlink()
            continue

    return deleted


# ---------------------------------------------------------------------------
# 03_KNOWLEDGE/ report
# ---------------------------------------------------------------------------

def lint_knowledge_tree(kb_root: Path) -> dict[str, object]:
    """Scan 03_KNOWLEDGE/ for orphans, broken links, name conflicts."""
    md_files = list(iter_md(kb_root))
    file_basenames = {p.stem: p for p in md_files}

    inbound: dict[str, set[str]] = defaultdict(set)
    broken: list[tuple[str, str]] = []
    name_map: dict[str, list[str]] = defaultdict(list)

    for md in md_files:
        text = md.read_text(encoding="utf-8", errors="ignore")
        body = FRONTMATTER_RE.sub("", text, count=1)
        rel = str(md.relative_to(kb_root.parent))
        for raw_target in link_targets(body):
            target = raw_target.strip()
            tail = target.split("/")[-1]
            if tail in file_basenames:
                inbound[file_basenames[tail].stem].add(rel)
            else:
                broken.append((rel, target))

        fm = read_frontmatter(md)
        if "name" in fm and fm["name"]:
            name_map[fm["name"].lower()].append(rel)

    orphans = [
        str(p.relative_to(kb_root.parent))
        for p in md_files
        if p.stem not in inbound and not p.name.startswith("_")
    ]
    conflicts = {name: paths for name, paths in name_map.items() if len(paths) > 1}

    return {
        "orphans": sorted(orphans),
        "broken_links": sorted(broken),
        "name_conflicts": conflicts,
    }


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(out_dir: Path, deleted: dict[str, list[str]], kb_report: dict[str, object]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    path = out_dir / f"{today}-lint.md"

    lines: list[str] = [
        "---",
        "type: meta",
        "title: Wiki Lint Report",
        f"date: {today}",
        "cssclasses: [graph-hide]",
        "---",
        "",
        f"# Wiki Lint Report — {today}",
        "",
    ]

    # wiki/ deletions
    lines.append("## Auto-deleted from `wiki/`")
    lines.append("")
    total = sum(len(v) for v in deleted.values())
    if total == 0:
        lines.append("_None. `wiki/` is clean._")
    else:
        for reason, items in sorted(deleted.items()):
            lines.append(f"### {reason} ({len(items)})")
            for item in items:
                lines.append(f"- `{item}`")
            lines.append("")

    # 03_KNOWLEDGE/ report
    lines.append("")
    lines.append("## `03_KNOWLEDGE/` — report only")
    lines.append("")

    orphans = kb_report["orphans"]
    lines.append(f"### Orphan pages ({len(orphans)})")
    lines.append("_Pages with zero inbound `[[wikilinks]]`._")
    lines.append("")
    for p in orphans:
        lines.append(f"- `{p}`")
    lines.append("")

    broken = kb_report["broken_links"]
    lines.append(f"### Broken `[[wikilinks]]` ({len(broken)})")
    lines.append("")
    for src, target in broken:
        lines.append(f"- `{src}` → `[[{target}]]`")
    lines.append("")

    conflicts = kb_report["name_conflicts"]
    lines.append(f"### Name conflicts ({len(conflicts)})")
    lines.append("_Same `name:` frontmatter in multiple files._")
    lines.append("")
    for name, paths in conflicts.items():
        lines.append(f"- **{name}**")
        for p in paths:
            lines.append(f"  - `{p}`")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def add_dashboard_notification(vault: Path, title: str, message: str, detailed_log: str, approve_cmd: str) -> None:
    """Append a notification to the dashboard Notification Center JSON."""
    import json
    import time
    
    noti_file = vault / "06_PLANNING" / "kpis" / "notifications.json"
    notifications = []
    if noti_file.exists():
        try:
            with open(noti_file, "r", encoding="utf-8") as f:
                notifications = json.load(f)
                if not isinstance(notifications, list):
                    notifications = []
        except Exception:
            notifications = []

    now_ms = int(time.time() * 1000)
    
    # Remove any existing unread wiki cleanup notifications to prevent spam
    notifications = [n for n in notifications if not (n.get("title") == title and not n.get("read"))]
    
    new_noti = {
        "id": f"wiki_lint_{now_ms}",
        "title": title,
        "message": message,
        "detailed_log": detailed_log,
        "approve_cmd": approve_cmd,
        "timestamp": now_ms,
        "read": False,
        "sound": True
    }
    notifications.append(new_noti)
    notifications = notifications[-20:]

    try:
        noti_file.parent.mkdir(parents=True, exist_ok=True)
        with open(noti_file, "w", encoding="utf-8") as f:
            json.dump(notifications, f, indent=2, ensure_ascii=False)
        print(f"Added dashboard notification: {title}")
    except Exception as e:
        print(f"Error writing notification: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Lint the Research vault wiki.")
    parser.add_argument("--vault-root", default=".", help="Vault root path.")
    parser.add_argument("--dry-run", action="store_true", help="Do not delete anything (default behavior).")
    parser.add_argument("--apply", action="store_true", help="Actually delete polluted wiki files.")
    parser.add_argument("--notify", action="store_true", help="Write dry-run report to dashboard Notification Center.")
    args = parser.parse_args()

    vault = Path(args.vault_root).resolve()
    wiki = vault / WIKI_DIR
    knowledge = vault / KNOWLEDGE_DIR
    lint_out = vault / LINT_OUT_DIR

    if not knowledge.exists():
        print(f"error: {knowledge} does not exist", file=sys.stderr)
        return 2

    # Default to dry-run unless --apply is explicitly set
    dry_run = True
    if args.apply:
        dry_run = False
    
    deleted = clean_wiki_tree(wiki, dry_run=dry_run)
    kb_report = lint_knowledge_tree(knowledge)
    report = write_report(lint_out, deleted, kb_report)

    total_deleted = sum(len(v) for v in deleted.values())
    print(f"Auto-{'would-delete' if dry_run else 'deleted'}: {total_deleted} from wiki/")
    print(f"Orphans:        {len(kb_report['orphans'])}")
    print(f"Broken links:   {len(kb_report['broken_links'])}")
    print(f"Name conflicts: {len(kb_report['name_conflicts'])}")
    print(f"Report:         {report.relative_to(vault)}")

    # Handle notification center injection
    if args.notify and total_deleted > 0:
        log_lines = []
        for reason, items in sorted(deleted.items()):
            log_lines.append(f"{reason} ({len(items)}):")
            for item in items:
                log_lines.append(f"  - {item}")
        detailed_log = "\n".join(log_lines)
        
        python_bin = sys.executable or "/usr/local/bin/python3.10"
        script_path = vault / "_scripts" / "automation" / "wiki_lint.py"
        approve_cmd = f"{python_bin} {script_path} --apply"
        
        add_dashboard_notification(
            vault=vault,
            title="🧹 Wiki Cleanup Proposed",
            message=f"Clean is recommended: {total_deleted} polluted files in wiki/.",
            detailed_log=detailed_log,
            approve_cmd=approve_cmd
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

