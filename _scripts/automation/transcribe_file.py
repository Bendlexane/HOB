#!/usr/bin/env python3
"""
transcribe_file.py — stamp a Whisper + Ollama transcript of an embedded audio
file directly under its `![[…]]` embed in a note.

STANDALONE / ex novo: this shares NO code with the conference recorder
(`transcribe_server.py`). It reads the same `_scripts/.env` for convenience,
but transcription, cleanup and note-insertion are all self-contained here.

Called by the Templater template `_scripts/templates/transcribe-audio.md`
(System & Utilities action), or directly:

    python _scripts/automation/transcribe_file.py \
        --audio "session-recording.m4a" \
        --note  "05_ADMIN/missions/conferences/2026_EXAMPLE/daily_notes/day-2.md"

Arguments:
    --audio    Audio file: absolute, vault-relative, or a bare filename resolved
               inside _attachments/. Any format ffmpeg/Whisper reads.
    --note     Target note: absolute or vault-relative.
    --session  Optional label shown in the callout header and used in the
               cleanup prompt. Defaults to the audio file's stem.

Config keys read from _scripts/.env:
    VAULT_ROOT, OLLAMA_HOST (or OLLAMA_URL), OLLAMA_MODEL, WHISPER_MODEL, WHISPER_LANG
"""

from __future__ import annotations   # `X | None` hints must work on macOS system Python 3.9

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# Live progress is surfaced in the Home dashboard's Notification Center, which
# polls this file every 5 s (_HOME.md). We keep ONE entry (NOTI_ID) and update
# it in place through the stages: Preparing → Whisper bar → Cleaning → done.
NOTI_REL = "06_PLANNING/kpis/notifications.json"
NOTI_ID = "transcribe_audio"
NOTI_TITLE = "🎙 Transcription"

# ─── Config ───────────────────────────────────────────────────────────────

def load_env() -> dict:
    cfg = {
        "vault_root": "",
        "ollama_url": "http://localhost:11434",
        "ollama_model": "gpt-oss:120b-cloud",
        "whisper_model": "medium",
        "whisper_lang": "auto",
    }
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip().lower()
            v = v.strip()
            if " #" in v:
                v = v.split(" #", 1)[0].strip()
            v = v.strip('"').strip("'")
            if k in ("ollama_host", "ollama_url"):
                cfg["ollama_url"] = v
            elif k == "vault_root":
                cfg["vault_root"] = v
            elif k == "ollama_model":
                cfg["ollama_model"] = v
            elif k == "whisper_model":
                cfg["whisper_model"] = v
            elif k == "whisper_lang":
                cfg["whisper_lang"] = v
    # environment overrides .env
    for env_key, cfg_key in (
        ("VAULT_ROOT", "vault_root"), ("OLLAMA_HOST", "ollama_url"),
        ("OLLAMA_URL", "ollama_url"), ("OLLAMA_MODEL", "ollama_model"),
        ("WHISPER_MODEL", "whisper_model"), ("WHISPER_LANG", "whisper_lang"),
    ):
        if os.environ.get(env_key):
            cfg[cfg_key] = os.environ[env_key]
    return cfg


CFG = load_env()

_LANG_NAMES = {
    "it": "Italian", "en": "English", "fr": "French", "de": "German",
    "es": "Spanish", "pt": "Portuguese", "nl": "Dutch", "sv": "Swedish",
}

# ─── Progress → Home Notification Center ───────────────────────────────────

# Session/vault are set once in main() so the Whisper progress hook (which has
# no easy way to receive params) can report without threading them through.
_NOTI = {"vault": "", "session": "", "enabled": True, "t": 0.0, "pct": None}


def _bar(pct: int | None, cells: int = 14) -> str:
    if pct is None:
        return ""
    n = max(0, min(100, int(pct)))
    filled = round(n / 100 * cells)
    return "█" * filled + "░" * (cells - filled) + f"  {n}%"


def _message(stage: str, percent: int | None, session: str) -> str:
    return {
        "starting":     f"Preparing “{session}”…",
        "loading":      "Loading Whisper model…",
        "transcribing": f"Whisper  {_bar(percent)}  · {session}",
        "cleaning":     f"🧹 Cleaning text with Ollama  · {session}",
        "done":         f"✅ Done — transcript added under “{session}”",
        "error":        f"❌ Failed — see /private/tmp/transcribe_file.log",
    }.get(stage, stage)


def _upsert_notification(vault: str, message: str, sound: bool) -> None:
    """Update (or create) the single 'transcribe_audio' entry, in place."""
    path = Path(vault) / NOTI_REL
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
    # Drop any previous copy, then append fresh so slice(-20) never evicts it.
    data = [n for n in data if n.get("id") != NOTI_ID]
    data.append({
        "id": NOTI_ID, "title": NOTI_TITLE, "message": message,
        "timestamp": int(time.time() * 1000), "read": False, "sound": sound,
    })
    data = data[-20:]
    try:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:  # noqa: BLE001
        print(f"[transcribe_file] notification write failed ({e})", file=sys.stderr)


def notify(stage: str, percent: int | None = None, *, force: bool = False) -> None:
    """Report a stage to the Home Notification Center (throttled for %)."""
    if not _NOTI["enabled"] or not _NOTI["vault"]:
        return
    now = time.time()
    # Throttle noisy Whisper ticks: skip unless ≥2% moved or ≥4 s passed.
    if not force and stage == "transcribing" and _NOTI["pct"] is not None and percent is not None:
        if abs(percent - _NOTI["pct"]) < 2 and (now - _NOTI["t"]) < 4:
            return
    _NOTI["t"], _NOTI["pct"] = now, percent
    sound = stage in ("done", "error")  # chime once at the end
    _upsert_notification(_NOTI["vault"], _message(stage, percent, _NOTI["session"]), sound)


def install_whisper_progress() -> None:
    """Route Whisper's internal tqdm through notify() (transcribing %)."""
    try:
        import whisper.transcribe as wt

        class _Bar:
            def __init__(self, *a, total=None, **k):
                self.total = total or 0
                self.n = 0
            def update(self, k=1):
                self.n += k
                pct = int(self.n / self.total * 100) if self.total else None
                notify("transcribing", pct)
            def close(self):
                pass
            def set_postfix(self, *a, **k):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                self.close()

        wt.tqdm.tqdm = _Bar  # whisper calls tqdm.tqdm(total=…); swap the class
    except Exception as e:  # noqa: BLE001
        print(f"[transcribe_file] progress hook unavailable ({e})", file=sys.stderr)

# ─── Whisper ──────────────────────────────────────────────────────────────

def _ensure_ffmpeg_on_path():
    """Whisper shells out to ffmpeg; make sure Homebrew paths are visible."""
    extra = ["/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin", "/usr/local/sbin"]
    cur = os.environ.get("PATH", "")
    for p in extra:
        if os.path.isdir(p) and p not in cur:
            cur = f"{p}:{cur}"
    os.environ["PATH"] = cur


def whisper_transcribe(audio_path: Path) -> tuple[str, str | None]:
    """Transcribe with Whisper, keeping the SOURCE language (never translate)."""
    import whisper  # lazy: the model import is heavy
    _ensure_ffmpeg_on_path()
    lang = CFG["whisper_lang"]
    lang = None if (not lang or str(lang).lower() in ("auto", "any", "detect")) else lang
    notify("loading", force=True)
    print(f"[transcribe_file] Loading Whisper model '{CFG['whisper_model']}'…", flush=True)
    model = whisper.load_model(CFG["whisper_model"])
    install_whisper_progress()
    notify("transcribing", 0, force=True)
    result = model.transcribe(str(audio_path), language=lang, task="transcribe")
    return result.get("text", "").strip(), result.get("language")

# ─── Ollama cleanup ───────────────────────────────────────────────────────

def ollama_clean(raw_text: str, session: str, language: str | None) -> str:
    """Remove fillers, fix punctuation, keep the SAME language. Returns raw on failure."""
    if not raw_text.strip():
        return raw_text
    lang_name = _LANG_NAMES.get((language or "").lower(), language) or "the same language as the transcript"
    prompt = (
        f"You are a scientific note editor.\n"
        f"The transcript is written in {lang_name}. You MUST write your entire output in {lang_name}. "
        f"NEVER translate it into another language.\n"
        f'Clean the following speech transcription from a recording titled "{session}".\n'
        f"Rules:\n"
        f"- The output language MUST be {lang_name} (identical to the input)\n"
        f"- Remove filler words (um, uh, ehm, cioè, like, you know)\n"
        f"- Fix obvious transcription errors and punctuation\n"
        f"- Keep all scientific content, speaker names, and key terms intact\n"
        f"- Italicize scientific (Latin) species names in Markdown, e.g. *Homo sapiens*\n"
        f"- Output plain text, no Markdown except the species italics above\n"
        f"- Do not summarize, translate, repeat, or invent content\n"
        f"- Output only the clean text, no meta-commentary\n\n"
        f"TRANSCRIPT:\n{raw_text}"
    )
    try:
        r = requests.post(
            f"{CFG['ollama_url'].rstrip('/')}/api/generate",
            json={"model": CFG["ollama_model"], "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.0}},
            timeout=180,
        )
        return r.json().get("response", raw_text).strip() or raw_text
    except Exception as e:  # noqa: BLE001
        print(f"[transcribe_file] Ollama cleanup failed ({e}) — using raw transcript", file=sys.stderr)
        return raw_text

# ─── Resolution + note insertion ──────────────────────────────────────────

def resolve_audio(audio: str, vault_root: Path) -> Path:
    cand = Path(audio)
    if cand.is_file():
        return cand
    if not cand.is_absolute() and (vault_root / audio).is_file():
        return vault_root / audio
    att = vault_root / "_attachments" / Path(audio).name
    if att.is_file():
        return att
    raise FileNotFoundError(f"Audio file not found: {audio}")


def resolve_note(note: str, vault_root: Path) -> Path:
    p = Path(note) if Path(note).is_absolute() else vault_root / note
    if not p.is_file():
        raise FileNotFoundError(f"Note not found: {p}")
    return p


def build_block(session: str, text: str, meta: str) -> str:
    body = "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))
    return (
        f"\n\n> [!quote]- Transcript — {session}\n"
        f"> <small>{meta}</small>\n>\n"
        f"{body}\n"
    )


def insert_after_embed(content: str, audio_name: str, block: str) -> tuple[str, bool]:
    """Insert `block` right after the line embedding `audio_name` (`![[…]]`)."""
    stem = re.escape(Path(audio_name).stem)
    embed = re.compile(
        rf"^.*!\[\[\s*{stem}(?:\.[A-Za-z0-9]+)?\s*(?:[#|][^\]]*)?\]\].*$",
        re.MULTILINE,
    )
    m = embed.search(content)
    if not m:
        return content, False
    return content[:m.end()] + block + content[m.end():], True

# ─── Main ─────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Transcribe an embedded audio file into its note.")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--note", required=True)
    ap.add_argument("--session", default=None)
    ap.add_argument("--no-dashboard", action="store_true",
                    help="Do not report progress to the Home Notification Center")
    args = ap.parse_args()

    vault_root = Path(CFG["vault_root"] or ".").resolve()
    _NOTI["vault"] = str(vault_root)
    _NOTI["enabled"] = not args.no_dashboard

    try:
        audio_path = resolve_audio(args.audio, vault_root)
        note_path = resolve_note(args.note, vault_root)
        session = args.session or audio_path.stem
        _NOTI["session"] = session
        notify("starting", force=True)

        print(f"[transcribe_file] audio : {audio_path}", flush=True)
        print(f"[transcribe_file] note  : {note_path}", flush=True)
        print(f"[transcribe_file] whisper={CFG['whisper_model']}  ollama={CFG['ollama_model']}  lang={CFG['whisper_lang']}", flush=True)

        raw, lang = whisper_transcribe(audio_path)
        print(f"[transcribe_file] raw transcript: {len(raw)} chars (language: {lang})", flush=True)
        if not raw.strip():
            print("[transcribe_file] ERROR: Whisper produced no text — aborting.", file=sys.stderr)
            notify("error", force=True)
            return 2

        notify("cleaning", 100, force=True)
        print("[transcribe_file] Ollama: cleaning…", flush=True)
        clean = ollama_clean(raw, session, lang) or raw
        print(f"[transcribe_file] clean transcript: {len(clean)} chars", flush=True)

        meta = f"Whisper {CFG['whisper_model']} · {(lang or '?')} · {datetime.now():%Y-%m-%d %H:%M}"
        content = note_path.read_text(encoding="utf-8")
        block = build_block(session, clean, meta)
        new_content, matched = insert_after_embed(content, audio_path.name, block)
        if not matched:
            print(f"[transcribe_file] WARNING: embed ![[{audio_path.name}]] not found — appending at end.", file=sys.stderr)
            new_content = content.rstrip() + "\n" + block
        note_path.write_text(new_content, encoding="utf-8")

        print(f"[transcribe_file] OK — transcript stamped into '{note_path.name}'.", flush=True)
        notify("done", 100, force=True)
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[transcribe_file] ERROR: {e}", file=sys.stderr)
        notify("error", force=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
