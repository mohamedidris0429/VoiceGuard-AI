"""Application settings loaded from environment variables / backend/.env.

No secret is hardcoded here. If SECRET_KEY is not supplied, a random key is
generated once and persisted to ``storage/.jwt_secret`` (git-ignored) so that
sessions survive a backend restart during local development.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application -------------------------------------------------
    app_name: str = "VoiceGuard AI"
    app_version: str = "1.0.0"
    environment: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api"

    # --- auth --------------------------------------------------------
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720

    # --- database ----------------------------------------------------
    database_url: str = (
        "postgresql+psycopg://voiceguard:voiceguard@127.0.0.1:5433/voiceguard"
    )
    db_echo: bool = False
    db_pool_size: int = 5

    # --- http --------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- storage / limits --------------------------------------------
    storage_dir: str = str(PROJECT_ROOT / "storage")
    max_upload_mb: int = 20
    min_audio_seconds: float = 1.0
    max_audio_seconds: float = 60.0
    min_sample_rate: int = 8000
    max_sample_rate: int = 192000

    # --- AI model ----------------------------------------------------
    model_id: str = "Vansh180/deepfake-audio-wav2vec2"
    model_cache_dir: str = str(PROJECT_ROOT / ".cache" / "huggingface")
    model_sample_rate: int = 16000
    model_window_seconds: float = 4.0
    model_max_windows: int = 3
    # Phase 2 - segment-wise detection plan (per request overrides allowed)
    segment_window_seconds: float = 4.0
    segment_hop_seconds: float = 2.0
    model_threads: int = 0  # 0 => auto (min(4, cpu_count))
    model_offline: bool = False
    synthetic_threshold: float = 0.5

    # --- rate limits (requests / window seconds) ---------------------
    rate_limit_auth: str = "10/60"
    rate_limit_analysis: str = "20/60"

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        """Resolve relative storage/model paths against the backend directory."""
        for field in ("storage_dir", "model_cache_dir"):
            value = getattr(self, field)
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = (BACKEND_DIR / path).resolve()
            object.__setattr__(self, field, str(path))
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir)

    @property
    def audio_dir(self) -> Path:
        return self.storage_path / "audio"

    @property
    def report_dir(self) -> Path:
        return self.storage_path / "reports"

    @property
    def tmp_dir(self) -> Path:
        return self.storage_path / "tmp"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def rate_limit(self, name: str) -> tuple[int, int]:
        raw = self.rate_limit_auth if name == "auth" else self.rate_limit_analysis
        try:
            count, window = raw.split("/", 1)
            return int(count), int(window)
        except (ValueError, AttributeError):
            return (10, 60)

    def get_secret_key(self) -> str:
        """Return the configured signing key, generating a persisted one if absent."""
        if self.secret_key:
            return self.secret_key
        key_path = self.storage_path / ".jwt_secret"
        try:
            if key_path.exists():
                stored = key_path.read_text(encoding="utf-8").strip()
                if len(stored) >= 32:
                    return stored
            key_path.parent.mkdir(parents=True, exist_ok=True)
            generated = secrets.token_urlsafe(64)
            key_path.write_text(generated, encoding="utf-8")
            return generated
        except OSError:  # pragma: no cover - unusual filesystem failure
            return secrets.token_urlsafe(64)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
