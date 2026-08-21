#!/usr/bin/env python3
"""Load runtime configuration from _scripts/.env.

Expected variables:
    VAULT_ROOT      — absolute path to the Obsidian vault
    ZOTERO_DB       — absolute path to zotero.sqlite
    ACTIVITYWATCH_URL — http://localhost:5600
    SEMANTIC_SCHOLAR_API_KEY — optional
    OLLAMA_HOST     — http://localhost:11434
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("config")

REQUIRED = frozenset({"VAULT_ROOT", "ZOTERO_DB"})
OPTIONAL = frozenset({
    "ACTIVITYWATCH_URL",
    "SEMANTIC_SCHOLAR_API_KEY",
    "OLLAMA_HOST",
    "ANTHROPIC_API_KEY",
    "MISTRAL_API_KEY",
    "OLLAMA_API_KEY",
    "OLLAMA_MODEL",
    "ICLOUD_EMAIL",
    "ICLOUD_APP_PASSWORD",
    "HPC_USER",
    "HPC_HOST",
    "CORDIS",
    "GEMINI_API_KEY",
    "ZOTERO_API_KEY",
    "ZOTERO_USER_ID",
    "WHISPER_LANG",
})

DEFAULTS = {
    "OLLAMA_HOST": "http://localhost:11434",
    "OLLAMA_MODEL": "gemma4:latest",
}


def find_dotenv(start_dir: Optional[Path] = None) -> Path:
    """Walk up from start_dir to find _scripts/.env."""
    # Search two roots: the caller's CWD, then this module's own location.
    # The second root is essential under launchd, which starts jobs with cwd=/
    # — a CWD-only walk would never reach the vault.
    roots = [(start_dir or Path.cwd()).resolve(), Path(__file__).resolve()]
    for root in roots:
        for parent in [root] + list(root.parents):
            # _scripts/.env is the canonical Python config (holds VAULT_ROOT,
            # ZOTERO_DB, …). A bare .env at the vault root is the Templater-only
            # file (AI_URL/AI_MODEL/TRANS_SERVER) and must NOT shadow it — so the
            # nested _scripts/.env is checked first.
            for candidate in [parent / "_scripts" / ".env", parent / ".env"]:
                if candidate.exists():
                    return candidate
    raise FileNotFoundError(
        "No .env found. Copy _scripts/.env.example to _scripts/.env "
        "and fill in VAULT_ROOT, ZOTERO_DB."
    )


def load(
    dotenv_path: Optional[Path] = None,
    require_all: bool = False,
) -> dict[str, str]:
    """Load .env and return {key: value}.

    Parameters
    ----------
    dotenv_path : Path, optional
        Explicit path to .env. If None, walks up from CWD.
    require_all : bool
        If True, raises on missing REQUIRED vars (default: logs a warning).
    """
    path = dotenv_path or find_dotenv()
    if not path.exists():
        raise FileNotFoundError(f".env not found at {path}")

    config: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        # Strip inline comments (space/tab before #)
        comment_pos = -1
        for q in ("'", '"'):
            if val.startswith(q):
                end = val.find(q, 1)
                if end > 0:
                    after = val[end + 1:].strip()
                    if after.startswith("#") or not after:
                        val = val[:end + 1]
                    comment_pos = -1
                    break
        else:
            if " #" in val:
                comment_pos = val.index(" #")
            elif "\t#" in val:
                comment_pos = val.index("\t#")
        if comment_pos >= 0:
            val = val[:comment_pos].strip()
        val = val.strip("\"'")
        config[key] = val

    for key in REQUIRED:
        if key not in config:
            msg = f"Missing required .env variable: {key}"
            if require_all:
                raise ValueError(msg)
            logger.warning(msg)

    for key, default in DEFAULTS.items():
        config.setdefault(key, default)

    return config


def env_as_dict() -> dict[str, str]:
    """Load .env once and return a dict for os.environ updates."""
    cfg = load()
    for key in list(cfg):
        os.environ.setdefault(key, cfg[key])
    return cfg
