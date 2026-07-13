from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    poll_interval_seconds: int = 60
    allowed_sender: str = "user@example.com"
    recipient: str = "user@example.com"
    gmail_account: str = "bridge@example.com"
    max_parallel_threads: int = 4
    gmail_query: str = "in:inbox from:user@example.com"
    codex_working_directory: str | None = None
    default_project: str | None = None
    projects: dict[str, str] = field(default_factory=dict)
    log_level: str = "INFO"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "bridge.sqlite3"


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "CodexGmailBridge"


def load_settings(path: Path | None = None) -> Settings:
    data_dir = default_data_dir()
    config_path = path or data_dir / "config.toml"
    raw = tomllib.loads(config_path.read_text("utf-8")) if config_path.exists() else {}
    return Settings(data_dir=data_dir, **raw)


def ensure_private_dirs(settings: Settings) -> None:
    for path in (settings.data_dir, settings.data_dir / "logs", settings.data_dir / "attachments"):
        path.mkdir(parents=True, exist_ok=True)
