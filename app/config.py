from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    backup_dir: Path
    environment: str
    username: str | None
    password: str | None
    timezone: str
    max_upload_bytes: int
    max_upload_files: int

    @property
    def auth_enabled(self) -> bool:
        return bool(self.username and self.password)

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("SECOND_BRAIN_DATA_DIR", "./data")).resolve()
        environment = os.getenv("SECOND_BRAIN_ENVIRONMENT", "development").strip().lower()
        settings = cls(
            data_dir=data_dir,
            database_path=Path(
                os.getenv("SECOND_BRAIN_DATABASE_PATH", str(data_dir / "second-brain.sqlite3"))
            ).resolve(),
            backup_dir=Path(
                os.getenv("SECOND_BRAIN_BACKUP_DIR", str(data_dir / "backups"))
            ).resolve(),
            environment=environment,
            username=os.getenv("SECOND_BRAIN_USERNAME") or None,
            password=os.getenv("SECOND_BRAIN_PASSWORD") or None,
            timezone=os.getenv("SECOND_BRAIN_TIMEZONE", "America/Sao_Paulo"),
            max_upload_bytes=int(os.getenv("SECOND_BRAIN_MAX_UPLOAD_BYTES", "5242880")),
            max_upload_files=int(os.getenv("SECOND_BRAIN_MAX_UPLOAD_FILES", "20")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("SECOND_BRAIN_ENVIRONMENT must be development, test, or production")
        if bool(self.username) != bool(self.password):
            raise ValueError("SECOND_BRAIN_USERNAME and SECOND_BRAIN_PASSWORD must be set together")
        if self.environment == "production" and not self.auth_enabled:
            raise ValueError("production requires HTTP Basic authentication credentials")
        if self.password and len(self.password) < 16:
            raise ValueError("SECOND_BRAIN_PASSWORD must contain at least 16 characters")
        if not 1_024 <= self.max_upload_bytes <= 25 * 1_024 * 1_024:
            raise ValueError("SECOND_BRAIN_MAX_UPLOAD_BYTES is outside the safe range")
        if not 1 <= self.max_upload_files <= 100:
            raise ValueError("SECOND_BRAIN_MAX_UPLOAD_FILES is outside the safe range")

    def prepare_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
