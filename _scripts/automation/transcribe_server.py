#!/usr/bin/env python3
"""
Conference session transcription server.

Listens on localhost:11435. Obsidian Templater buttons POST here to
start/stop audio recording. On stop, runs Whisper transcription and
Ollama cleanup, then appends the result to the target note.

Usage:
    python _scripts/automation/transcribe_server.py          # default port 11435
    python _scripts/automation/transcribe_server.py --port 11435

Dependencies (add to requirements.txt):
    sounddevice
    soundfile
    openai-whisper
    flask
    numpy

.env variables read:
    VAULT_ROOT         absolute path to vault
    OLLAMA_URL         default http://localhost:11434
    OLLAMA_MODEL       default gpt-oss:120b-cloud
    WHISPER_MODEL      default medium
    WHISPER_LANG       default en
"""

import argparse
import json
import logging
import os
import queue
import re
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

import numpy as np
import requests
import sounddevice as sd
import soundfile as sf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("transcribe_server")

# ─── Config ───────────────────────────────────────────────────────────

def load_env() -> dict:
    env_path = Path(__file__).parent.parent / ".env"
    cfg: dict = {
        "vault_root": "",
        "ollama_url": "http://localhost:11434",
        "ollama_model": "gemma4:latest",
        "whisper_model": "medium",
        "whisper_lang": ["en", "auto"],
    }
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip().lower()
            v = v.strip()
            # strip inline comments ("value   # comment") and surrounding quotes
            if " #" in v:
                v = v.split(" #", 1)[0].strip()
            v = v.strip('"').strip("'")
            if k == "vault_root":
                cfg["vault_root"] = v
            elif k == "ollama_url":
                cfg["ollama_url"] = v
            elif k == "ollama_model":
                cfg["ollama_model"] = v
            elif k == "whisper_model":
                cfg["whisper_model"] = v
            elif k == "whisper_lang":
                cfg["whisper_lang"] = v
    # env vars override .env
    for k in ("VAULT_ROOT", "OLLAMA_URL", "OLLAMA_MODEL", "WHISPER_MODEL", "WHISPER_LANG"):
        if os.environ.get(k):
            cfg[k.lower()] = os.environ[k]
    return cfg


CFG = load_env()

# ─── Recording state ──────────────────────────────────────────────────

class RecordingState:
    def __init__(self):
        self._lock = threading.Lock()
        self.active = False
        self.note_path: Optional[str] = None
        self.session_name: Optional[str] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._frames: list = []
        self.samplerate: int = 16000  # actual capture rate, set when stream opens

    def start(self, note_path: str, session_name: str) -> bool:
        with self._lock:
            if self.active:
                return False
            self.active = True
            self.note_path = note_path
            self.session_name = session_name
            self._frames = []
            self._stop_event.clear()
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()
        log.info("Recording started for session '%s'", session_name)
        return True

    def stop(self) -> Optional[tuple[str, str]]:
        """Stop recording. Returns (note_path, session_name) or None if idle."""
        with self._lock:
            if not self.active:
                return None
            note_path = self.note_path
            session_name = self.session_name
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        with self._lock:
            self.active = False
        log.info("Recording stopped for session '%s'", session_name)
        return note_path, session_name

    def get_frames(self) -> list:
        with self._lock:
            return list(self._frames)

    def _record_loop(self):
        channels = 1

        def callback(indata, frames, time, status):
            if status:
                log.warning("sounddevice status: %s", status)
            if not self._stop_event.is_set():
                with self._lock:
                    self._frames.append(indata.copy())

        # Capture at the input device's NATIVE samplerate. Forcing 16 kHz fails
        # on devices that don't support it natively (e.g. AirPods @ 24 kHz) with
        # CoreAudio error -10851 / PortAudio -9986. Whisper resamples to 16 kHz
        # via ffmpeg regardless, so native capture is fine; we store the actual
        # rate for the WAV header.
        try:
            native_sr = int(sd.query_devices(kind="input")["default_samplerate"])
        except Exception:
            native_sr = None

        for attempt_sr in (native_sr, None):
            try:
                kwargs = dict(channels=channels, dtype="float32", callback=callback)
                if attempt_sr:
                    kwargs["samplerate"] = attempt_sr
                with sd.InputStream(**kwargs) as stream:
                    self.samplerate = int(stream.samplerate)
                    try:
                        dev_name = sd.query_devices(kind="input")["name"]
                    except Exception:
                        dev_name = "unknown"
                    log.info("Microphone open at %d Hz (device: %s)", self.samplerate, dev_name)
                    self._stop_event.wait()
                return
            except Exception as e:
                log.error("InputStream open failed (samplerate=%s): %s", attempt_sr, e)

        log.error("Could not open any microphone input stream — recording will be empty. "
                  "Check System Settings > Privacy & Security > Microphone, and the selected input device.")


_state = RecordingState()

# ─── Background-job progress (for the Obsidian progress indicator) ─────
_job_lock = threading.Lock()
_job = {"stage": "idle", "session": None, "updated": 0.0}

def _set_stage(stage: str, session: Optional[str] = None):
    with _job_lock:
        _job["stage"] = stage
        if session is not None:
            _job["session"] = session
        _job["updated"] = time.time()

# ─── Idle Shutdown Timer ──────────────────────────────────────────────
_last_active_time = time.time()
TIMEOUT_SECONDS = 900  # 15 minutes

def idle_check_loop():
    global _last_active_time
    log.info("Idle shutdown timer started (timeout: %d seconds)", TIMEOUT_SECONDS)
    while True:
        time.sleep(30)
        # If currently recording, reset active time so we don't time out
        if _state.active:
            _last_active_time = time.time()
            continue
        
        # If currently transcribing or cleaning, reset active time
        with _job_lock:
            stage = _job.get("stage", "idle")
        if stage not in ("idle", "done", "error"):
            _last_active_time = time.time()
            continue

        elapsed = time.time() - _last_active_time
        if elapsed > TIMEOUT_SECONDS:
            log.info("Idle timeout reached (%.1f seconds). Auto-shutting down...", elapsed)
            os._exit(0)

# ─── Whisper ──────────────────────────────────────────────────────────

_whisper_model_cache = None

def get_whisper_model():
    global _whisper_model_cache
    if _whisper_model_cache is None:
        import whisper
        log.info("Loading Whisper model '%s'…", CFG["whisper_model"])
        _whisper_model_cache = whisper.load_model(CFG["whisper_model"])
    return _whisper_model_cache


def _recordings_dir(note_path: str) -> Path:
    """Derive a `_recordings/` folder at the mission root (two levels up from daily_notes/)."""
    p = Path(note_path)
    return p.parent.parent / "_recordings"


def save_frames(frames: list, note_path: str, session_name: str, samplerate: int = 16000) -> Path:
    """Concatenate frames, save as WAV in _recordings/, return path."""
    from datetime import datetime
    if not frames:
        raise ValueError("No frames to save")
    audio = np.concatenate(frames, axis=0).flatten()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug  = re.sub(r"[^a-zA-Z0-9]+", "_", session_name).strip("_")[:60]
    out   = _recordings_dir(note_path) / f"{slug}_{stamp}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), audio, samplerate)
    log.info("Audio saved: %s (%d samples @ %d Hz)", out, len(audio), samplerate)
    return out


def transcribe_file(wav_path: Path) -> tuple[str, Optional[str]]:
    """Transcribe a WAV file with Whisper. Returns (text, detected_language).

    task="transcribe" keeps the SOURCE language (task="translate" would force
    English — we never want that here)."""
    model = get_whisper_model()
    lang = CFG["whisper_lang"]
    # Whisper needs a real language code or None — it does NOT accept "auto".
    # Normalise: a list (e.g. ["en","auto"]), a string code ("it"/"en"), or
    # "auto"/empty. None → Whisper auto-detects per recording (English, Italian…);
    # a specific code forces that language.
    if isinstance(lang, (list, tuple)):
        lang = None if any(str(x).lower() in ("auto", "any", "detect") for x in lang) else (lang[0] if lang else None)
    elif not lang or str(lang).lower() in ("auto", "any", "detect"):
        lang = None
    result = model.transcribe(str(wav_path), language=lang, task="transcribe")
    return result.get("text", "").strip(), result.get("language")

# ─── Ollama cleanup ───────────────────────────────────────────────────

_LANG_NAMES = {
    "it": "Italian", "en": "English", "fr": "French", "de": "German",
    "es": "Spanish", "pt": "Portuguese", "nl": "Dutch", "sv": "Swedish",
}

def ollama_clean(raw_text: str, session_name: str, language: Optional[str] = None) -> str:
    """Remove filler words, fix punctuation, return clean prose IN THE SAME LANGUAGE."""
    if not raw_text.strip():
        return raw_text
    lang_name = _LANG_NAMES.get((language or "").lower(), language) or "the same language as the transcript below"
    prompt = (
        f"You are a scientific note editor.\n"
        f"The transcript is written in {lang_name}. You MUST write your entire output in {lang_name}. "
        f"NEVER translate it into another language — preserve the original language exactly.\n"
        f'Clean the following speech transcription from a conference session titled "{session_name}".\n'
        f"Rules:\n"
        f"- The output language MUST be {lang_name} (identical to the input language)\n"
        f"- Remove filler words (um, uh, ehm, cioè, like, you know)\n"
        f"- Fix obvious transcription errors\n"
        f"- Keep all scientific content, speaker names, and key terms intact\n"
        f"- Italicize scientific (Latin) names of species in Markdown, e.g. *Homo sapiens*, *Quercus robur*\n"
        f"- Output plain text, with NO Markdown except the italics for scientific names above\n"
        f"- Do not summarize, translate, repeat, or invent content\n"
        f"- Output only the clean text of the talk, no meta-commentary\n\n"
        f"TRANSCRIPT:\n{raw_text}"
    )
    try:
        r = requests.post(
            f"{CFG['ollama_url']}/api/generate",
            json={"model": CFG["ollama_model"], "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.0}},
            timeout=60,
        )
        return r.json().get("response", raw_text).strip()
    except Exception as e:
        log.warning("Ollama cleanup failed (%s) — using raw transcript", e)
        return raw_text

# ─── Note append ──────────────────────────────────────────────────────

def append_to_note(note_path: str, session_name: str, text: str, vault_root: str) -> bool:
    """
    Append the transcription block under the matching session heading.
    If the heading is not found, appends at the end of the note.
    """
    full_path = Path(vault_root) / note_path if not Path(note_path).is_absolute() else Path(note_path)
    if not full_path.exists():
        log.error("Note not found: %s", full_path)
        return False

    content = full_path.read_text(encoding="utf-8")
    block = (
        f"\n\n> [!quote] Recorded intervention — {session_name}\n"
        + "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))
        + "\n"
    )

    # Try to insert after the matching session heading (any level #–######)
    import re
    # Match the session_name at any heading level, capturing up to the next heading (any level) or EOF
    pattern = re.compile(
        rf"(#{{1,6}}\s*{re.escape(session_name)}.*?)(?=\n#|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(content)
    if match:
        insert_pos = match.end(1)
        updated = content[:insert_pos] + block + content[insert_pos:]
    else:
        # Fallback: append at end of file
        updated = content.rstrip() + "\n" + block

    full_path.write_text(updated, encoding="utf-8")
    log.info("Transcription appended to '%s' under '%s'", note_path, session_name)
    return True

# ─── HTTP handler ─────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # silence default access log
        log.debug(format, *args)

    def _read_json(self) -> Optional[dict]:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length))

    def _respond(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok", "recording": _state.active})
        elif self.path == "/status":
            with _job_lock:
                self._respond(200, dict(_job))
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        global _last_active_time
        _last_active_time = time.time()
        data = self._read_json() or {}

        # ── POST /record/start ────────────────────────────────────────
        if self.path == "/record/start":
            note_path    = data.get("note_path", "")
            session_name = data.get("session_name", "")
            if not note_path or not session_name:
                self._respond(400, {"status": "error", "message": "note_path and session_name required"})
                return
            # Quick microphone probe — catch "no input device / lid closed" before
            # accepting the session so the user gets an alert immediately.
            try:
                import sounddevice as _sd
                dev_info = _sd.query_devices(kind="input")
                native_sr = int(dev_info["default_samplerate"])
                with _sd.InputStream(samplerate=native_sr, channels=1, dtype="float32"):
                    pass  # just open and close
            except Exception as mic_err:
                log.error("Microphone probe failed at /record/start: %s", mic_err)
                self._respond(200, {
                    "status": "no_mic",
                    "message": f"Microphone not available: {mic_err}",
                    "session_name": session_name,
                })
                return
            started = _state.start(note_path, session_name)
            if started:
                self._respond(200, {"status": "ok", "message": f"Recording started for '{session_name}'"})
            else:
                self._respond(409, {"status": "error", "message": "A recording is already active"})

        # ── POST /record/stop ─────────────────────────────────────────
        elif self.path == "/record/stop":
            result = _state.stop()
            if result is None:
                self._respond(200, {"status": "idle", "message": "No active recording"})
                return

            note_path, session_name = result
            frames = _state.get_frames()

            if not frames:
                self._respond(200, {"status": "empty", "message": "Recording was empty — no audio captured (check microphone permission / input device)", "session_name": session_name})
                return

            # Run the heavy work (Whisper model load + transcription + Ollama
            # cleanup) in a BACKGROUND thread so the HTTP handler returns
            # immediately. Otherwise the request blocks the server until the
            # ~1.5 GB Whisper model finishes loading and /health times out.
            def process():
                wav_path = None
                try:
                    wav_path = save_frames(frames, note_path, session_name, _state.samplerate)

                    _set_stage("transcribing", session_name)
                    raw, raw_lang = transcribe_file(wav_path)
                    log.info("Transcription raw length: %d chars (detected language: %s)", len(raw), raw_lang)

                    _set_stage("cleaning", session_name)
                    clean = ollama_clean(raw, session_name, raw_lang)
                    log.info("Clean transcript length: %d chars", len(clean))
                    # If cleanup blanked the text but Whisper produced content,
                    # fall back to the raw transcript rather than inserting nothing.
                    if not clean.strip() and raw.strip():
                        log.warning("Cleanup returned empty — using raw transcript")
                        clean = raw

                    ok = append_to_note(note_path, session_name, clean, CFG["vault_root"])
                    if ok:
                        log.info("Transcript appended to note OK")
                        _set_stage("done", session_name)
                        # Clean up audio only on success
                        wav_path.unlink(missing_ok=True)
                    else:
                        log.error("append_to_note returned False for %s", note_path)
                        _set_stage("error", session_name)
                except Exception:
                    log.exception("Background transcription failed")
                    _set_stage("error", session_name)
                    if wav_path and wav_path.exists():
                        log.warning("Audio preserved at %s for manual retry", wav_path)

            _set_stage("transcribing", session_name)  # immediate, before thread spins up
            threading.Thread(target=process, daemon=True).start()
            self._respond(200, {
                "status": "ok",
                "session_name": session_name,
                "message": "Processing transcription in background — check the note in a moment",
            })

        else:
            self._respond(404, {"status": "error", "message": "endpoint not found"})


# ─── Entrypoint ───────────────────────────────────────────────────────

def main():
    # Ensure common macOS Homebrew and other PATHs are included (Whisper needs ffmpeg)
    extra = [
        "/opt/homebrew/bin", "/opt/homebrew/sbin",
        "/usr/local/bin", "/usr/local/sbin",
    ]
    cur = os.environ.get("PATH", "")
    for p in extra:
        if os.path.isdir(p) and p not in cur:
            cur = f"{p}:{cur}"
    os.environ["PATH"] = cur

    ap = argparse.ArgumentParser(description="Conference session transcription server")
    ap.add_argument("--port", type=int, default=11435)
    args = ap.parse_args()

    if not CFG["vault_root"]:
        log.warning("VAULT_ROOT not set in .env — note paths will be resolved as absolute")

    # ThreadingHTTPServer: each request in its own thread, so a slow handler
    # (or background transcription) never blocks /health or the next click.
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)

    # Start the idle check daemon thread
    t = threading.Thread(target=idle_check_loop, daemon=True)
    t.start()

    log.info("Transcription server listening on http://127.0.0.1:%d", args.port)
    log.info("Whisper model: %s | Ollama model: %s", CFG["whisper_model"], CFG["ollama_model"])
    log.info("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Server stopped")


if __name__ == "__main__":
    main()
