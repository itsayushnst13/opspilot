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
    demo_password: str = "opspilot-demo"  # demo users only; set your own in prod
    allow_self_approval: bool = False
    expose_demo_users: bool = True  # shows demo logins on the login page (this is a public demo)

    # Uploads / storage
    max_upload_mb: int = 5
    storage_dir: Path = Path("./storage")
    data_dir: Path = REPO_ROOT / "data"
    max_pdf_pages: int = 30
    max_sheet_rows: int = 5000

    # LLM (Gemini). If no key is set the system runs in deterministic "rules" mode.
    gemini_api_key: Optional[str] = Field(default=None)
    gemini_model: str = "gemini-3.6-flash"
    # Tried in order if the primary model name is rejected as not found (model names get retired).
    gemini_fallback_models: str = "gemini-3.8-flash,gemini-2.5-flash"
    # None = model default. Gemini 3 models recommend the default; set 0 for 2.x models if you want determinism.
    gemini_temperature: Optional[float] = None
    gemini_embed_model: str = "gemini-embedding-001"
    # auto = Gemini embeddings when a key is set; hashing = always the deterministic local embedder.
    # Embeddings have their own quota, so a shared demo on a free key is steadier on "hashing".
    embedder: str = "auto"  # auto | hashing | gemini
    embed_dim: int = 768
    # Optional reasoning depth ("minimal" | "low" | "medium" | "high"). Unset = the model's own default.
    # Sent as generationConfig.thinkingLevel; if a model rejects it the client retries once without it.
    gemini_thinking_level: Optional[str] = None
    llm_mode: str = "auto"  # auto | llm | rules
    llm_timeout_s: float = 60.0          # per HTTP request
    llm_total_budget_s: float = 90.0     # whole call: retries across every fallback model
    agent_max_steps: int = 12

    # Pin 'today' for RFQ processing. The synthetic price lists are valid until a fixed date, so a public demo
    # pins this (e.g. 2026-10-01) to keep working; leave unset to use the real date.
    reference_date: Optional[dt.date] = None

    # Serving
    cors_origins: str = "http://localhost:5173"
    static_dir: Optional[Path] = None  # built frontend, served by FastAPI if set

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
