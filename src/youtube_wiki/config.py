from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    data_dir: Path
    raw_dir: Path
    cache_dir: Path
    database_path: Path
    log_level: str

    @classmethod
    def load(cls, project_root: Path | None = None) -> Settings:
        root = (project_root or Path.cwd()).resolve()
        load_dotenv(root / ".env")
        configured = Path(os.getenv("YOUTUBE_WIKI_DATA_DIR", "data"))
        data_dir = configured if configured.is_absolute() else root / configured
        return cls(
            api_key=os.getenv("YOUTUBE_API_KEY") or None,
            data_dir=data_dir,
            raw_dir=data_dir / "raw",
            cache_dir=data_dir / "cache",
            database_path=data_dir / "cache" / "state.sqlite3",
            log_level=os.getenv("YOUTUBE_WIKI_LOG_LEVEL", "INFO").upper(),
        )

    def ensure_directories(self) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

