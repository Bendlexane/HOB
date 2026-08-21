#!/usr/bin/env python3.10
"""
zotero_export_background.py — Background worker for literature note synthesis.
Reads exported metadata and highlights from a temporary JSON, extracts PDF text,
calls Ollama (gpt-oss:120b-cloud), formats the note, writes it to Obsidian,
and sends notifications to the HOB dashboard.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# Add _scripts/ to path to load config and literature modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.config import load as load_config
from utils.literature import build_frontmatter, slugify_citekey

# ── Load Configuration ────────────────────────────────────────────────────────
cfg = load_config()
OLLAMA_HOST = cfg.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = cfg.get("OLLAMA_MODEL", "gpt-oss:120b-cloud")
VAULT_ROOT = cfg.get("VAULT_ROOT") or sys.exit(
    "❌ VAULT_ROOT not set — copy _scripts/.env.example to _scripts/.env and fill it in."
)

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("❌ PyMuPDF (fitz) is required. Install it using: pip3.10 install pymupdf")

# ── HOB Dashboard Notification Helper ─────────────────────────────────────────
def notify(title: str, message: str, sound: bool = True):
    noti_path = Path(VAULT_ROOT) / "06_PLANNING/kpis/notifications.json"
    try:
        if noti_path.exists():
            try:
                notis = json.loads(noti_path.read_text(encoding="utf-8"))
            except Exception:
                notis = []
        else:
            notis = []
            
        if not isinstance(notis, list):
            notis = []

        import random
        new_noti = {
            "id": f"{time.time() * 1000}_{random.random()}",
            "title": title,
            "message": message,
            "timestamp": int(time.time() * 1000),
            "read": False,
            "sound": sound
        }
        notis.append(new_noti)
        notis = notis[-20:]  # Keep only the last 20 notifications
        
        noti_path.parent.mkdir(parents=True, exist_ok=True)
        noti_path.write_text(json.dumps(notis, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"Error writing notification: {e}", file=sys.stderr)

# ── Ollama HTTP Client ────────────────────────────────────────────────────────
def call_ollama(prompt: str, system_prompt: str = "You are a scientific research assistant.") -> str:
    url = f"{OLLAMA_HOST}/v1/chat/completions"
    data = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "stream": False
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    # 3-minute timeout for 120B model
    with urllib.request.urlopen(req, timeout=180) as response:
        res = json.loads(response.read().decode("utf-8"))
        return res["choices"][0]["message"]["content"]

# ── Callout Helper ────────────────────────────────────────────────────────────
def make_markdown_callout(c_type: str, title: str, content: str) -> str:
    lines = content.split("\n")
    callout_lines = [f"> [!{c_type}] {title}"]
    for line in lines:
        callout_lines.append(f"> {line}" if line else ">")
    return "\n".join(callout_lines)

# ── Callout Formatting Parser ─────────────────────────────────────────────────
def format_as_callouts(text: str) -> str:
    if not text or not text.strip():
        return "_No analysis available._"

    callout_map = {
        "context (introduction)": "quote",
        "context":                "quote",
        "aims":                   "info",
        "thesis":                 "abstract",
        "methods":                "example",
        "key findings":           "success",
        "conclusions":            "tip",
        "broader significance / novelty": "info",
        "broader significance":   "info",
        "limitations":            "warning",
    }

    def resolve_type(cat_lower):
        key = re.sub(r'\s*\(.*?\)\s*', ' ', cat_lower).strip()
        if key in callout_map:
            return callout_map[key]
        for k, v in callout_map.items():
            if key.startswith(k) or k.startswith(key):
                return v
        return "note"

    q_pattern = r"[\"“”]"
    arrow_pattern = r"(?:→|->|>)"
    
    blocks = []
    pending_cat = None
    
    for raw in text.split("\n"):
        line = raw.strip()
        line = re.sub(r'^[-*+]\s+', '', line)
        line = re.sub(r'^>\s*', '', line).strip()
        if not line:
            continue
            
        m_quote = re.match(r"^(.*?)" + q_pattern + r"(.+?)" + q_pattern + r"\s*" + arrow_pattern + r"?\s*(.*)$", line)
        if m_quote:
            inline_cat = m_quote.group(1).strip("*:>\u2192 ")
            cat = inline_cat if inline_cat else pending_cat
            if cat:
                quote = m_quote.group(2).replace("*", "").strip()
                interp = m_quote.group(3).replace("*", "").strip()
                c_type = resolve_type(cat.lower())
                
                # Clean category title
                c_title = re.sub(r'[*_\-\s\u2011\u2013\u2014]+$', '', cat)
                c_title = c_title.replace('*', '').replace('_', '').strip()
                c_title = c_title[0].upper() + c_title[1:] if c_title else cat
                
                content = f'"{quote}"\n\n*{interp}*'
                blocks.append(make_markdown_callout(c_type, c_title, content))
            pending_cat = None
            continue
            
        m_ns = re.match(r"^(.*?)\s*[:>\u2192]?\s*Not explicitly stated\.?$", line, re.IGNORECASE)
        if m_ns:
            inline_cat = m_ns.group(1).strip("*:>\u2192 ")
            cat = inline_cat if inline_cat else pending_cat
            if cat:
                c_type = resolve_type(cat.lower())
                
                # Clean category title
                c_title = re.sub(r'[*_\-\s\u2011\u2013\u2014]+$', '', cat)
                c_title = c_title.replace('*', '').replace('_', '').strip()
                c_title = c_title[0].upper() + c_title[1:] if c_title else cat
                
                content = "*Not explicitly stated.*"
                blocks.append(make_markdown_callout(c_type, c_title, content))
            pending_cat = None
            continue
            
        cat_only = line.strip("*:>\u2192 ")
        if cat_only and len(cat_only) <= 60:
            pending_cat = cat_only
            
    return "\n\n".join(blocks) if blocks else text

def process_synthesis_response(text: str) -> str:
    # Search for reflection separator using robust regex (case-insensitive)
    # Target "reflection" with optional "free-form", "critical", or "riflessione" as fallback
    parts = re.split(
        r'(?i)(?:^|\n)(?:#+\s+|\*+)?(?:(?:\d+\.)?\s*)?(?:(?:free[- \u2011\u2013\u2014]form\s+)?reflection|riflessione\s+(?:libera|critica))(?::|\*+|\s)*',
        text,
        maxsplit=1
    )
    if len(parts) == 2:
        cat_part, reflection_part = parts
        formatted_cats = format_as_callouts(cat_part)
        reflection_clean = reflection_part.strip(" \n*:-#>")
        
        reflection_block = make_markdown_callout("thought", "Theoretical & Critical Reflection", reflection_clean)
        return f"{formatted_cats}\n\n{reflection_block}"
    else:
        return format_as_callouts(text)

# ── Annotations Formatting Helper ─────────────────────────────────────────────
def format_annotations(annotations_list: list, header_level: int = 3) -> str:
    if not annotations_list:
        return ""
    
    groups = {}
    for ann in annotations_list:
        lbl = ann.get("color_label", "other")
        groups.setdefault(lbl, []).append(ann)

    COLOR_ORDER = ["red", "yellow", "green", "blue", "purple", "orange", "pink", "grey"]
    COLOR_EMOJI = {"red":"🔴", "pink":"🩷", "yellow":"🟡", "green":"🟢", "blue":"🔵", "purple":"🟣", "orange":"🟠", "grey":"⚫"}
    
    ordered_labels = [l for l in COLOR_ORDER if l in groups] + [l for l in groups if l not in COLOR_ORDER]

    hl_section = ""
    hashes = "#" * header_level
    for lbl in ordered_labels:
        emoji = COLOR_EMOJI.get(lbl, "◆")
        label_str = lbl.capitalize()
        hl_section += f"{hashes} {emoji} {label_str}\n\n"
        for ann in groups[lbl]:
            page = ann.get("page", "")
            page_str = f"p. {page}" if page else ""
            if ann.get("type") == "note":
                comment_body = ann.get("comment") or ann.get("text") or "*(empty)*"
                hl_section += f"- **[Note{', ' + page_str if page_str else ''}]** {comment_body}\n"
            else:
                hl_section += f"- **[{page_str}]** “{ann.get('text', '*(empty)*')}”\n"
                if ann.get("comment"):
                    hl_section += f"  > *{ann.get('comment')}*\n"
        hl_section += "\n"
        
    return hl_section

# ── PDF Extraction & Chapter Boundary Fallback ─────────────────────────────
def detect_chapters_llm_fallback(doc: fitz.Document, doc_title: str) -> list[dict]:
    pages_first_chars = []
    # Scan at most 100 pages to avoid prompt bloat
    max_scan_pages = min(len(doc), 100)
    for pno in range(max_scan_pages):
        text = doc[pno].get_text()
        first_chars = text.strip()[:300].replace('\n', ' ')
        pages_first_chars.append(f"Page {pno + 1}: {first_chars}")
        
    pages_summary = "\n".join(pages_first_chars)
    
    prompt = f"""You are a document analyzer. Given the first 300 characters of each page of a book titled "{doc_title}", identify the page numbers where a new chapter or main section begins.
Look for patterns like "Chapter X", "Capitolo X", or section titles that are bold and centered at the start of the page.

Return ONLY a JSON list of the starting page numbers (e.g., [1, 15, 34, 52]). Do not include any explanations or markdown formatting, return only the raw JSON array.

Page starts:
{pages_summary}"""
    
    try:
        response_text = call_ollama(prompt, system_prompt="You are a precise assistant for document analysis. Return only JSON.")
        cleaned = re.sub(r'```[a-zA-Z]*', '', response_text).strip('` \n\t')
        start_pages = json.loads(cleaned)
        if isinstance(start_pages, list) and len(start_pages) > 0:
            start_pages = sorted([int(p) for p in start_pages if str(p).isdigit()])
            if 1 not in start_pages:
                start_pages.insert(0, 1)
            
            chapters = []
            for idx, p in enumerate(start_pages):
                start = p
                end = start_pages[idx+1] - 1 if idx < len(start_pages) - 1 else len(doc)
                chapters.append({
                    "title": f"Chapter starting at page {start}",
                    "start_page": start,
                    "end_page": end
                })
            return chapters
    except Exception as e:
        print(f"Chapter detection via LLM failed: {e}", file=sys.stderr)
        
    # Final fallback: 15-page chunks
    chapters = []
    chunk_size = 15
    for start in range(1, len(doc) + 1, chunk_size):
        end = min(start + chunk_size - 1, len(doc))
        chapters.append({
            "title": f"Pages {start}-{end}",
            "start_page": start,
            "end_page": end
        })
    return chapters

def extract_chapters(pdf_path: str, doc_title: str) -> list[dict]:
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()
    
    chapters = []
    if toc:
        level_1 = [entry for entry in toc if entry[0] == 1]
        if not level_1:
            level_1 = [entry for entry in toc if entry[0] == 2]
            
        if level_1:
            for idx, entry in enumerate(level_1):
                level, title, page = entry
                start_page = page
                if idx < len(level_1) - 1:
                    end_page = level_1[idx+1][2] - 1
                else:
                    end_page = len(doc)
                chapters.append({
                    "title": title,
                    "start_page": start_page,
                    "end_page": end_page
                })
                
    if not chapters:
        chapters = detect_chapters_llm_fallback(doc, doc_title)
        
    for ch in chapters:
        ch_text = ""
        for pno in range(ch["start_page"] - 1, min(ch["end_page"], len(doc))):
            ch_text += f"\n--- Page {pno + 1} ---\n"
            ch_text += doc[pno].get_text()
        ch["text"] = ch_text
        
    doc.close()
    return chapters

# ── Main Worker ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Background worker for literature note synthesis.")
    parser.add_argument("--json", required=True, help="Path to temporary JSON file")
    # NOTE: pdf/dest/project are read from the JSON file (UTF-8 safe). The argv
    # flags below are kept only as a fallback: nsIProcess.run() mangles non-ASCII
    # bytes in argv on macOS (dropping em-dashes, curly apostrophes, accents),
    # which corrupts PDF paths. Prefer the JSON values.
    parser.add_argument("--pdf", default="", help="(fallback) Path to source PDF file")
    parser.add_argument("--dest", default="", help="(fallback) Destination directory in Obsidian vault")
    parser.add_argument("--project", default="", help="(fallback) Project code")
    args = parser.parse_args()

    # 1. Load data from temp JSON
    json_path = Path(args.json)
    if not json_path.exists():
        sys.exit(f"❌ JSON file not found: {json_path}")
        
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        sys.exit(f"❌ Failed to parse JSON: {e}")

    citekey = data.get("citekey", "unknown")
    title = data.get("title", "(no title)")
    authors = data.get("authors", [])
    year = data.get("year", "")
    journal = data.get("journal", "")
    abstract = data.get("abstract", "")
    mode = str(data.get("mode", "1"))
    annotations = data.get("annotations", [])

    # Read pdf/dest/project from the JSON (UTF-8 safe), falling back to argv.
    # See the argparse note above: argv drops non-ASCII bytes on macOS, so the
    # JSON values are authoritative when present.
    pdf_path = data.get("pdf") or args.pdf
    dest_dir = data.get("dest") or args.dest
    project = data.get("project") or args.project
    if not dest_dir:
        sys.exit("❌ No destination directory provided (JSON 'dest' or --dest).")

    # Notify start
    notify("Progress", f"Background synthesis started for: {citekey}.md", sound=False)

    try:
        synthesis = ""
        synth_source = OLLAMA_MODEL
        unassigned_annotations = list(annotations)

        # Mode 1: Highlights Only (Standard Mode)
        if mode == "1":
            # Format annotations
            hl_ctx = []
            for ann in annotations:
                p = ann.get("page", "")
                page_lbl = f"[p.{p}] " if p else ""
                hl_ctx.append(f"{page_lbl}{ann.get('text', '')}")
            hl_text = "\n".join(hl_ctx)

            prompt = f"""Summarize using ONLY the evidence directly present in the provided text. Every statement must be anchored to the source material.

For each category, provide a textual quote (exact and in quotes) and a concise interpretation (one or more sentences as needed):

Context (introduction) > "[quote]" → [interpretation]
Aims > "[quote]" → [interpretation]
Thesis > "[quote]" → [interpretation]
Methods > "[quote]" → [interpretation]
Key Findings > "[quote]" → [interpretation]
Conclusions > "[quote]" → [interpretation]
Broader significance / novelty > "[quote]" → [interpretation]
Limitations > "[quote]" → [interpretation]

If a category cannot be supported by a direct quote, write "Not explicitly stated."
Preserve technical terminology. Respond in English.

Title: {title}
Authors: {"; ".join(authors)}
Year: {year}
Journal: {journal}

Abstract:
{abstract[:2000]}

Key Highlights:
{hl_text}

Be specific and scientific. Respond in English."""
            
            raw_synthesis = call_ollama(prompt, system_prompt="You are a scientific research assistant. Be concise and precise.")
            synthesis = format_as_callouts(raw_synthesis)

        # Mode 2: Full-Text Synthesis (For Papers)
        elif mode == "2":
            if not pdf_path or not Path(pdf_path).exists():
                raise FileNotFoundError(f"PDF not found: {pdf_path}")

            # Extract entire PDF text
            doc = fitz.open(pdf_path)
            full_text = ""
            for page in doc:
                full_text += f"\n--- Page {page.number + 1} ---\n"
                full_text += page.get_text()
            doc.close()

            prompt = f"""Summarize the paper using ONLY the evidence directly present in the text. Every statement must be anchored to the source material.

1. CATEGORY SYNTHESIS:
For each category, provide a textual quote (exact and in quotes) and a concise interpretation (one or more sentences as needed):

Context (introduction) > "[quote]" → [interpretation]
Aims > "[quote]" → [interpretation]
Thesis > "[quote]" → [interpretation]
Methods > "[quote]" → [interpretation]
Key Findings > "[quote]" → [interpretation]
Conclusions > "[quote]" → [interpretation]
Broader significance / novelty > "[quote]" → [interpretation]
Limitations > "[quote]" → [interpretation]

If a category cannot be supported by a direct quote, write "Not explicitly stated."

2. FREE-FORM REFLECTION:
At the end of the analysis, provide a critical reflection/free-form synthesis of the paper, discussing its implications, novel contributions, theoretical connections, and your scientific/philosophical assessment of the text.

Preserve technical terminology. Respond in English.

Title: {title}
Authors: {"; ".join(authors)}
Year: {year}
Journal: {journal}

Abstract:
{abstract}

Full paper text:
{full_text}"""
            
            raw_synthesis = call_ollama(prompt, system_prompt="You are a scientific research assistant. Be concise, precise, and analytical.")
            synthesis = process_synthesis_response(raw_synthesis)

        # Mode 3: Chapter-by-Chapter Synthesis (For Books)
        elif mode == "3":
            if not pdf_path or not Path(pdf_path).exists():
                raise FileNotFoundError(f"PDF not found: {pdf_path}")

            chapters = extract_chapters(pdf_path, title)
            
            chapter_blocks = []
            for idx, ch in enumerate(chapters):
                # Filter highlights belonging to this chapter (and remove from unassigned)
                ch_anns = []
                ch_highlights_prompt = []
                for ann in list(unassigned_annotations):
                    try:
                        page_val = ann.get("page", "0")
                        match = re.search(r'\d+', str(page_val))
                        pno = int(match.group(0)) if match else 0
                        if pno > 0 and ch["start_page"] <= pno <= ch["end_page"]:
                            ch_anns.append(ann)
                            ch_highlights_prompt.append(f"[p.{page_val}] {ann.get('text', '')}")
                            unassigned_annotations.remove(ann)
                    except Exception:
                        pass
                ch_hl_text = "\n".join(ch_highlights_prompt)

                prompt = f"""Analyze the following chapter text from the book "{title}". 
Provide a concise synthesis of this chapter, summarizing:
1. The main argument, theme, or narrative of the chapter.
2. Key concepts and definitions introduced.
3. Main conclusions or historical/theoretical context.

4. FREE-FORM CHAPTER REFLECTION:
Provide a free-form analytical reflection on the arguments, implications, and theoretical strength of this chapter.

Respond in English. Use paragraphs or bullet points where appropriate.

Chapter: {ch['title']} (Pages {ch['start_page']} to {ch['end_page']})

Chapter text:
{ch['text']}"""

                # Optional chapter highlights to retain grounding
                if ch_hl_text:
                    prompt += f"\n\nHighlights in this chapter:\n{ch_hl_text}"

                raw_ch_synth = call_ollama(prompt, system_prompt="You are a scientific research assistant. Summarize the chapters of the book in a text-grounded and analytical manner.")
                
                # Split response into synthesis and reflection
                parts = re.split(
                    r'(?i)(?:^|\n)(?:#+\s+|\*+)?(?:(?:\d+\.)?\s*)?(?:free[- \u2011\u2013\u2014]form\s+)?(?:chapter\s+)?reflection(?::|\*+|\s)*',
                    raw_ch_synth,
                    maxsplit=1
                )
                    
                ch_summary_formatted = parts[0].strip()
                ch_block = f"### {ch['title']} (Pages {ch['start_page']}-{ch['end_page']})\n\n{ch_summary_formatted}"
                
                if len(parts) == 2:
                    ch_reflection = parts[1].strip(" \n*:-#>")
                    ch_block += "\n\n" + make_markdown_callout("thought", "Chapter Reflection", ch_reflection)
                
                # Append chapter-specific annotations if any
                if ch_anns:
                    ch_block += "\n\n#### Personal Annotations\n\n" + format_annotations(ch_anns, header_level=5).rstrip()

                chapter_blocks.append(ch_block)
            
            synthesis = "\n\n---\n\n".join(chapter_blocks)

        # ── 9. Generate YAML frontmatter ──────────────────────────────────────
        fm = build_frontmatter(
            citekey,
            stage="litnote",
            status="synthesized",
            authors=authors,
            year=int(year) if year.isdigit() else None,
            journal=journal,
            doi=data.get("doi", ""),
            project_code=[project] if project else None,
            tags=data.get("tags", []),
            source="zotero",
            title=title,
        )

        # ── 10. Build Custom Annotations Section ─────────────────────────────
        if mode == "3":
            # For Mode 3, only show unassigned annotations at the bottom
            hl_section = format_annotations(unassigned_annotations, header_level=3).rstrip()
        else:
            hl_section = format_annotations(annotations, header_level=3).rstrip()

        # ── 11. Assemble Finished Document ───────────────────────────────────
        document = [
            fm,
            "",
            f"# {title}",
            "",
            "## Abstract",
            "",
            abstract.strip() or "_No abstract available._",
            "",
            "## Full analysis",
            "",
            f"*(gpt-oss:120b-cloud — {datetime.now().strftime('%Y-%m-%d')})*",
            "",
            synthesis,
        ]

        if hl_section:
            document.extend([
                "",
                "## Personal Annotations",
                "",
                hl_section,
            ])

        document.extend([
            "",
            "---",
            "",
            "## Personal consideration",
            "",
            "",
        ])
        
        final_doc = "\n".join(document)

        # ── 12. Write Final File ──────────────────────────────────────────────
        dest_file = Path(dest_dir) / f"{citekey}.md"
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(final_doc, encoding="utf-8")

        # Clean up temporary JSON
        if json_path.exists():
            json_path.unlink()

        notify("Success", f"Synthesis completed and exported: {citekey}.md")
        print(f"✅ Synthesis successfully completed for {citekey}.md")

    except Exception as e:
        notify("Error", f"Synthesis failed for {citekey}: {str(e)}")
        print(f"❌ Synthesis failed: {e}", file=sys.stderr)
        # Clean up temp JSON on failure too
        if json_path.exists():
            try:
                json_path.unlink()
            except Exception:
                pass
        sys.exit(1)

if __name__ == "__main__":
    main()
