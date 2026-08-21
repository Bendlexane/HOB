#!/usr/bin/env python3
"""Vault path resolution — all paths relative to VAULT_ROOT."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from utils.config import load


class VaultPaths:
    """Resolved paths inside the vault, derived from VAULT_ROOT."""

    def __init__(self, vault_root: Optional[Path] = None) -> None:
        cfg = load()
        root = vault_root or Path(cfg["VAULT_ROOT"]).resolve()
        self.root: Path = root
        self.scripts: Path = root / "_scripts"
        self.kpi: Path = self.scripts / "kpi"
        self.utils: Path = self.scripts / "utils"
        self.kpi_db: Path = root / "06_PLANNING" / "kpis" / "research_kpis.db"
        self.kpi_schema: Path = root / "06_PLANNING" / "kpis" / "research_kpis_schema.sql"
        self.kpi_exports: Path = root / "06_PLANNING" / "kpis" / "exports"
        self.tag_prompt: Path = self.kpi / "tag_prompt.txt"
        self.dotenv: Path = self.scripts / ".env"

    def ensure_kpi_dir(self) -> Path:
        db_dir = self.kpi_db.parent
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir
