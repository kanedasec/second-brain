from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta

from app.backup import create_backup, next_friday_run, prune_backups


def test_backup_is_consistent_and_has_checksum(settings):
    connection = sqlite3.connect(settings.database_path)
    connection.execute("CREATE TABLE notes (value TEXT NOT NULL)")
    connection.execute("INSERT INTO notes VALUES ('remember this')")
    connection.commit()
    connection.close()

    backup = create_backup(
        settings.database_path,
        settings.backup_dir,
        datetime(2026, 10, 30, 23, 55, tzinfo=UTC),
    )
    assert backup.exists()
    assert backup.with_suffix(".sqlite3.sha256").exists()
    restored = sqlite3.connect(backup)
    assert restored.execute("SELECT value FROM notes").fetchone()[0] == "remember this"
    restored.close()


def test_prune_removes_backups_older_than_three_month_window(settings):
    settings.backup_dir.mkdir()
    old = settings.backup_dir / "second-brain-older.sqlite3"
    recent = settings.backup_dir / "second-brain-recent.sqlite3"
    old.write_bytes(b"old")
    recent.write_bytes(b"recent")
    old_checksum = old.with_suffix(".sqlite3.sha256")
    old_checksum.write_text("checksum")
    now = datetime(2026, 10, 28, tzinfo=UTC)
    old_time = (now - timedelta(days=94)).timestamp()
    os.utime(old, (old_time, old_time))
    os.utime(old_checksum, (old_time, old_time))

    removed = prune_backups(settings.backup_dir, now=now)
    assert removed == [old]
    assert not old_checksum.exists()
    assert recent.exists()


def test_next_backup_is_end_of_friday_in_configured_timezone():
    wednesday = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    scheduled = next_friday_run(wednesday, "America/Sao_Paulo")
    assert scheduled.weekday() == 4
    assert (scheduled.hour, scheduled.minute) == (23, 55)

    late_friday = datetime(2026, 10, 31, 3, 30, tzinfo=UTC)
    following = next_friday_run(late_friday, "America/Sao_Paulo")
    assert following.date().isoformat() == "2026-11-06"
