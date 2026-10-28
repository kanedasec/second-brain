from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import Settings


RETENTION_DAYS = 93


def create_backup(database_path: Path, backup_dir: Path, now: datetime | None = None) -> Path:
    if not database_path.is_file():
        raise FileNotFoundError(f"database does not exist: {database_path}")
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
    timestamp = (now or datetime.now().astimezone()).astimezone().strftime("%Y%m%dT%H%M%S%z")
    destination = backup_dir / f"second-brain-{timestamp}.sqlite3"
    temporary = destination.with_suffix(".sqlite3.tmp")

    source_connection = sqlite3.connect(database_path)
    destination_connection = sqlite3.connect(temporary)
    try:
        source_connection.backup(destination_connection)
        integrity = destination_connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"backup integrity check failed: {integrity}")
    finally:
        destination_connection.close()
        source_connection.close()

    os.chmod(temporary, 0o640)
    temporary.replace(destination)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    checksum_path = destination.with_suffix(destination.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {destination.name}\n", encoding="ascii")
    os.chmod(checksum_path, 0o640)
    return destination


def prune_backups(backup_dir: Path, now: datetime | None = None, retention_days: int = RETENTION_DAYS) -> list[Path]:
    cutoff = (now or datetime.now().astimezone()).timestamp() - retention_days * 86_400
    removed: list[Path] = []
    if not backup_dir.exists():
        return removed
    for path in backup_dir.glob("second-brain-*.sqlite3"):
        if path.stat().st_mtime < cutoff:
            checksum = path.with_suffix(path.suffix + ".sha256")
            path.unlink()
            removed.append(path)
            if checksum.exists():
                checksum.unlink()
    return removed


def next_friday_run(now: datetime, timezone_name: str, hour: int = 23, minute: int = 55) -> datetime:
    zone = ZoneInfo(timezone_name)
    local_now = now.astimezone(zone)
    days_ahead = (4 - local_now.weekday()) % 7
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(
        days=days_ahead
    )
    if candidate <= local_now:
        candidate += timedelta(days=7)
    return candidate


def run_scheduler(settings: Settings) -> None:
    settings.prepare_directories()
    while True:
        now = datetime.now().astimezone()
        scheduled = next_friday_run(now, settings.timezone)
        seconds = max(1, (scheduled - now.astimezone(scheduled.tzinfo)).total_seconds())
        print(f"next backup scheduled for {scheduled.isoformat()}", flush=True)
        time.sleep(seconds)
        for attempt in range(1, 4):
            try:
                backup = create_backup(
                    settings.database_path,
                    settings.backup_dir,
                    datetime.now(ZoneInfo(settings.timezone)),
                )
                removed = prune_backups(settings.backup_dir)
                print(
                    f"backup created: {backup.name}; expired backups removed: {len(removed)}",
                    flush=True,
                )
                break
            except Exception as error:
                print(
                    f"backup attempt {attempt}/3 failed: {type(error).__name__}: {error}",
                    flush=True,
                )
                if attempt < 3:
                    time.sleep(300)


if __name__ == "__main__":
    run_scheduler(Settings.from_env())
