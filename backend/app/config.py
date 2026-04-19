from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PCA_",
        extra="ignore",
    )

    # --- App ---
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # --- Paths ---
    data_dir: Path = Field(default_factory=_default_data_dir)

    # --- Dropbox OAuth ---
    # Register a Dropbox app at https://www.dropbox.com/developers/apps and put
    # the values in backend/.env (see .env.example).
    dropbox_app_key: str = ""
    dropbox_app_secret: str = ""
    dropbox_redirect_uri: str = "http://localhost:8000/api/auth/dropbox/callback"

    # --- LAN access shared-secret token ---
    # Set in .env to require ?token=... on first visit. Empty disables auth.
    access_token: str = ""

    # --- Session / cookie signing ---
    session_secret: str = "dev-secret-change-me"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "catalog.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def faces_dir(self) -> Path:
        return self.data_dir / "faces"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def tokens_path(self) -> Path:
        return self.data_dir / "dropbox_tokens.json"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.thumbnails_dir, self.faces_dir, self.models_dir):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
