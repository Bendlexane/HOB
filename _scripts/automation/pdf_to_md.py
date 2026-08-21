#!/usr/bin/env python3.10
"""
pdf_to_md.py — Convert a PDF to Markdown.

Backends:
  marker   — marker_single CLI (fast, best layout, academic papers)
  glm-ocr  — Ollama GLM-OCR vision model (for scanned/image-only PDFs)

Usage:
    python3.10 pdf_to_md.py <pdf> <output.md> --backend marker|glm-ocr
                            [--dpi 150] [--dry-run]
"""

import argparse
import base64
import datetime
import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Make _scripts/ importable so `utils.literature` resolves regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Citekey for the literature schema, set from --citekey in main().
_CITEKEY: str | None = None

try:
    import fitz
except ImportError:
    sys.exit("❌ pymupdf not installed: pip3.10 install pymupdf")

MODEL_GLM = "glm-ocr:latest"
DEFAULT_DPI = 150
SYSTEM_PROMPT_GLM = (
    "You are an OCR assistant. Extract all text from the provided page image "
    "and render it in clean Markdown. Preserve headings, lists, tables, and "
    "emphasis where visible. Output only the Markdown transcription."
)


def _load_env() -> dict:
    env_path = Path(__file__).parent.parent / ".env"
    cfg = {}
    if not env_path.exists():
        return cfg
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def _is_literature_dest(output_path: Path) -> bool:
    """True when the note lands in 03_KNOWLEDGE/literature/ (citekey schema applies)."""
    return "03_KNOWLEDGE/literature" in output_path.as_posix()


def _frontmatter(
    pdf_path: Path, n_pages: int, backend: str,
    output_path: Path, citekey: str | None = None,
) -> str:
    """Build frontmatter.

    Literature destination → canonical citekey schema (literature.schema.yaml),
    so OCR-imported notes are indistinguishable from Templater/Zotero ones (C4).
    Any other destination (methods/, staging) → light generic frontmatter, no
    citekey requirement and no Title-Case mangling.
    """
    title = pdf_path.stem  # raw stem — no .title() mangling
    if _is_literature_dest(output_path):
        from utils.literature import build_frontmatter, slugify_citekey
        ck = slugify_citekey(citekey or output_path.stem or pdf_path.stem)
        fm = build_frontmatter(
            ck,
            title=title,
            source="pdf-ocr",
            source_pdf=pdf_path.name,
            ocr_backend=backend,
            pages=n_pages,
        )
        return (
            fm + "\n"
            f"# {title}\n\n"
            f"> Converted from `{pdf_path.name}` via `{backend}` — "
            f"review and fill bibliographic fields before archiving.\n\n"
        )
    # Non-literature note (methods, protocol import, staging scratch).
    today = datetime.date.today().isoformat()
    return (
        f"---\n"
        f"type: reference\n"
        f'title: "{title}"\n'
        f'source_pdf: "{pdf_path.name}"\n'
        f"pages: {n_pages}\n"
        f"ocr_backend: {backend}\n"
        f"date_imported: {today}\n"
        f"tags: []\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"> Converted from `{pdf_path.name}` via `{backend}` — review before archiving.\n\n"
    )


def _find_assets_dir(output_path: Path) -> tuple[Path, str]:
    """Locate the centralized assets folder and compute relative path from output."""
    current = output_path.parent.resolve()
    while current.name != "03_KNOWLEDGE" and current != current.parent:
        current = current.parent
    if current.name == "03_KNOWLEDGE":
        assets_dir = current / "_assets" / "pdf-figures"
    else:
        assets_dir = output_path.parent / "_assets" / "pdf-figures"
    assets_dir.mkdir(parents=True, exist_ok=True)
    rel_assets = os.path.relpath(assets_dir, output_path.parent.resolve())
    return assets_dir, rel_assets


def _rewrite_image_refs(content: str, rel_assets: str, pdf_stem: str) -> str:
    """Rewrite marker image refs (![](_page_X_Figure_Y.jpeg)) to centralized path."""
    def _replacer(m: re.Match) -> str:
        img_name = m.group(1)
        new_name = f"{pdf_stem}_{img_name}"
        return f"]({rel_assets}/{new_name}"
    return re.sub(r'\]\((_page_\d+_(?:Figure|Picture)_\d+\.jpe?g)\)', _replacer, content)


# ── backend: marker ────────────────────────────────────────────────────────────

def _convert_marker(pdf_path: Path, output_path: Path, dry_run: bool) -> None:
    marker_bin = shutil.which("marker_single") or str(
        Path.home() / "Library/Python/3.10/bin/marker_single"
    )
    if not Path(marker_bin).exists():
        sys.exit("❌ marker_single not found")

    doc = fitz.open(str(pdf_path))
    n_pages = len(doc)
    doc.close()

    print(f"📄 {pdf_path.name}  ({n_pages} pages)", flush=True)
    print(f"⚙️  backend: marker_single", flush=True)

    # marker creates <output_dir>/<pdf_stem>/<pdf_stem>.md — use parent of output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    marker_subdir = output_path.parent / pdf_path.stem
    expected_md   = marker_subdir / f"{pdf_path.stem}.md"

    cmd = [
        marker_bin,
        str(pdf_path),
        "--output_dir", str(output_path.parent),
        "--output_format", "markdown",
    ]
    if dry_run:
        cmd += ["--page_range", "0"]

    print(f"⚙️  cmd: {' '.join(cmd)}", flush=True)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in proc.stdout:
        print(line, end="", flush=True)
    proc.wait()

    print(f"⚙️  exit code: {proc.returncode}", flush=True)
    if proc.returncode != 0:
        sys.exit(f"❌ marker_single failed (exit {proc.returncode})")

    # marker always writes to <output_dir>/<pdf_stem>/<pdf_stem>.md
    print(f"⚙️  expected: {expected_md}", flush=True)
    if not expected_md.exists():
        sys.exit(f"❌ marker output not found at {expected_md}")

    content = expected_md.read_text(encoding="utf-8")

    if dry_run:
        print("\n── DRY RUN (first 2000 chars) ────────────────────────────\n")
        print(content[:2000])
        print("\n──────────────────────────────────────────────────────────")
        print("(no file written)")
        # clean up marker's subfolder
        if marker_subdir.exists():
            shutil.rmtree(marker_subdir)
        return

    # Copy extracted images to centralized _assets/ and rewrite references
    assets_dir, rel_assets = _find_assets_dir(output_path)
    pdf_stem = pdf_path.stem
    if marker_subdir.exists():
        for img in marker_subdir.glob("*_page_*_*"):
            if img.is_file() and img.suffix.lower() in (".jpeg", ".jpg", ".png", ".gif", ".webp"):
                new_name = f"{pdf_stem}_{img.name}"
                shutil.copy2(img, assets_dir / new_name)
    content = _rewrite_image_refs(content, rel_assets, pdf_stem)
    # Prepend frontmatter and save
    full = _frontmatter(pdf_path, n_pages, "marker", output_path, _CITEKEY) + content
    output_path.write_text(full, encoding="utf-8")
    if marker_subdir.exists():
        shutil.rmtree(marker_subdir)
    print(f"✅ Saved: {output_path}", flush=True)


# ── backend: pymupdf4llm (fast, text-based PDFs) ─────────────────────────────

def _convert_fast(pdf_path: Path, output_path: Path, dry_run: bool) -> None:
    import pymupdf4llm

    doc = fitz.open(str(pdf_path))
    n_pages = len(doc)
    doc.close()

    print(f"📄 {pdf_path.name}  ({n_pages} pages)", flush=True)
    print(f"⚙️  backend: pymupdf4llm", flush=True)

    md_text = pymupdf4llm.to_markdown(str(pdf_path))

    if dry_run:
        print("\n── DRY RUN (first 2000 chars) ────────────────────────────\n")
        print(md_text[:2000])
        print("\n──────────────────────────────────────────────────────────")
        print("(no file written)")
        return

    full = _frontmatter(pdf_path, n_pages, "pymupdf4llm", output_path, _CITEKEY) + md_text
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full, encoding="utf-8")
    print(f"✅ Saved: {output_path}", flush=True)


# ── backend: glm-ocr ──────────────────────────────────────────────────────────

def _convert_glm(pdf_path: Path, output_path: Path, dpi: int, dry_run: bool) -> None:
    try:
        import ollama
    except ImportError:
        sys.exit("❌ ollama not installed: pip3.10 install ollama")

    cfg = _load_env()
    host = cfg.get("OLLAMA_HOST", "http://localhost:11434")
    api_key = cfg.get("OLLAMA_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    client = ollama.Client(host=host, headers=headers)

    doc = fitz.open(str(pdf_path))
    n_pages = len(doc)
    print(f"📄 {pdf_path.name}  ({n_pages} pages, {dpi} DPI)", flush=True)
    print(f"⚙️  backend: glm-ocr", flush=True)

    pages_md = []
    for i, page in enumerate(doc, start=1):
        if dry_run and i > 1:
            break
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
        print(f"  page {i}/{n_pages} …", flush=True)
        resp = client.generate(
            model=MODEL_GLM,
            prompt=SYSTEM_PROMPT_GLM,
            images=[b64],
            options={"num_predict": 8192},
        )
        pages_md.append(f"<!-- page {i} -->\n\n{resp.response.strip()}")
        print(f"  page {i} ✓", flush=True)

    doc.close()

    if dry_run:
        print("\n── DRY RUN (page 1) ──────────────────────────────────────\n")
        print(pages_md[0][:2000])
        print("\n──────────────────────────────────────────────────────────")
        print("(no file written)")
        return

    full = _frontmatter(pdf_path, n_pages, "glm-ocr", output_path, _CITEKEY) + "\n\n---\n\n".join(pages_md)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full, encoding="utf-8")
    print(f"✅ Saved: {output_path}", flush=True)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Convert PDF to Markdown")
    ap.add_argument("pdf", help="Source PDF path")
    ap.add_argument("output", help="Output .md path")
    ap.add_argument(
        "--backend", choices=["fast", "marker", "glm-ocr"], default="fast",
        help="Conversion backend (default: fast)",
    )
    ap.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    ap.add_argument(
        "--citekey", default=None,
        help="Citekey for literature notes (literature.schema.yaml). "
             "Defaults to the output filename stem when omitted.",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    global _CITEKEY
    _CITEKEY = args.citekey

    pdf = Path(args.pdf.strip())
    out = Path(args.output.strip())

    if not pdf.exists():
        sys.exit(f"❌ PDF not found: {pdf}")

    if args.backend == "fast":
        _convert_fast(pdf, out, args.dry_run)
    elif args.backend == "marker":
        _convert_marker(pdf, out, args.dry_run)
    else:
        _convert_glm(pdf, out, args.dpi, args.dry_run)


if __name__ == "__main__":
    main()
