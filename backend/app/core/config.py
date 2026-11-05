"""Application settings, loaded from environment variables (see .env.example)."""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    env: str = "dev"  # dev | prod
    database_url: str = "sqlite:///./opspilot.db"

    # Auth
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_expire_minutes: int = 480
    demo_password: str = "opspilot-demo"  # must be overridden in production
    allow_self_approval: bool = False
    expose_demo_users: bool = False  # opt in explicitly for a public demo

    # Uploads / storage
    max_upload_mb: int = 5
    storage_dir: Path = Path("./storage")
    data_dir: Path = REPO_ROOT / "data"
    max_pdf_pages: int = 30
    max_sheet_rows: int = 5000

    # LLM (Gemini). If no key is set the system runs in deterministic "rules" mode.
    gemini_api_key: Optional[str] = Field(default=None)
    gemini_model: str = "gemini-3.6-flash"
    gemini_fallback_models: str = "gemini-3.8-flash,gemini-2.5-flash"
    gemini_temperature: Optional[float] = None
    gemini_embed_model: str = "gemini-embedding-001"
    embedder: str = "auto"
    embed_dim: int = 768
    gemini_thinking_level: Optional[str] = None
    llm_mode: str = "auto"
    llm_timeout_s: float = 60.0
    llm_total_budget_s: float = 90.0
    agent_max_steps: int = 12

    reference_date: Optional[dt.date] = None

    # Serving
    cors_origins: str = "http://localhost:5173"
    static_dir: Optional[Path] = None

    @property
    def today(self) -> dt.date:
        return self.reference_date or dt.date.today()

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def effective_mode(self) -> str:
        if self.llm_mode == "rules":
            return "rules"
        if self.llm_mode == "llm":
            return "llm"
        return "llm" if self.gemini_api_key else "rules"


@lru_cache
def get_settings() -> Settings:
    return Settings()
