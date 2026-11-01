"""Consistent SQLite snapshots and restores to a new file; never overwrite a database."""

import sqlite3
import time
from contextlib import closing
from pathlib import Path


def copy_database(source: Path, destination: Path) -> None:
    original = source.resolve(strict=True)
    target = destination.resolve()
    if not original.is_file() or original == target:
        raise ValueError("Choose a database file and a different, new destination")
    # Exclusive creation protects existing files, including an active database.
    with target.open("xb"):
        pass
    deadline = time.monotonic() + 30

    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() > deadline:
            raise TimeoutError("Database snapshot exceeded its time budget")

    try:
        with closing(
            sqlite3.connect(original.as_uri() + "?mode=ro", uri=True, timeout=5)
        ) as reader:
            with closing(sqlite3.connect(target, timeout=5)) as writer:
                reader.backup(writer, pages=128, progress=progress, sleep=0.05)
                if writer.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError("Database integrity check failed")
    except BaseException:
        target.unlink(missing_ok=True)
        raise
