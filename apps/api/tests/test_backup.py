import sqlite3

import pytest

from sowcast.storage.backup import copy_database


def test_backup_restore_and_overwrite_protection(tmp_path):
    source, backup, restored = (tmp_path / name for name in ("live.db", "backup.db", "restored.db"))
    with sqlite3.connect(source) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE evidence(value TEXT)")
        writer.execute("INSERT INTO evidence VALUES ('preserved')")
        writer.commit()
        copy_database(source, backup)
    copy_database(backup, restored)
    with sqlite3.connect(restored) as reader:
        assert reader.execute("SELECT value FROM evidence").fetchall() == [("preserved",)]
    original = source.read_bytes()
    with pytest.raises(FileExistsError):
        copy_database(backup, source)
    assert source.read_bytes() == original
    with pytest.raises(ValueError):
        copy_database(source, source)


def test_invalid_backup_removes_incomplete_destination(tmp_path):
    source, destination = tmp_path / "invalid.db", tmp_path / "new.db"
    source.write_text("not a database")
    with pytest.raises(sqlite3.DatabaseError):
        copy_database(source, destination)
    assert not destination.exists()
