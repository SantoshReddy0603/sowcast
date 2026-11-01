import asyncio
import json
import os
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from test_backtest import END, NOW, START, evidence

from sowcast.backtest.metrics import assess
from sowcast.backtest.store import BacktestStore
from sowcast.storage.database import Database
from sowcast.storage.traces import TraceStore


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
async def test_empty_migration_and_records(backend, tmp_path):
    admin = None
    name = "sowcast_test_" + uuid4().hex
    if backend == "postgresql":
        url = os.environ.get("TEST_DATABASE_URL")
        if not url:
            pytest.skip("TEST_DATABASE_URL is not configured")
        admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
        location = make_url(url).set(database=name).render_as_string(hide_password=False)
    else:
        location = str(tmp_path / "empty.sqlite3")
    db = Database(location)
    try:
        async with db.engine.connect() as connection:
            assert await connection.run_sync(lambda c: inspect(c).get_table_names()) == []
        await db.initialize()
        await db.initialize()
        async with db.engine.connect() as connection:
            assert set(await connection.run_sync(lambda c: inspect(c).get_table_names())) == {
                "alembic_version",
                "traces",
                "backtest_jobs",
                "backtest_results",
            }
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
            )
        traces = TraceStore(db)
        await traces.save(str(uuid4()), {"token": "private"})
        jobs = BacktestStore(db)
        results = await asyncio.gather(jobs.claim("plot", "one"), jobs.claim("plot", "two"))
        assert sorted(results) == [False, True]
        owner = "one" if results[0] else "two"
        forecast, reference = await evidence()
        result = assess(forecast, reference, START, END, NOW)
        await jobs.finish("plot", "wrong-owner", result)
        assert await jobs.claim("plot", "other") is False
        await jobs.finish("plot", owner, result)
        second = BacktestStore(db)
        assert await second.claim("plot", "other") == result
        async with db.transaction() as session:
            body = await session.scalar(text("SELECT body FROM traces"))
            assert json.loads(body)["token"] == "[redacted]"
    finally:
        await db.close()
        if admin:
            async with admin.connect() as connection:
                await connection.execute(text(f'DROP DATABASE "{name}"'))
            await admin.dispose()


@pytest.mark.asyncio
async def test_existing_sqlite_trace_is_preserved(tmp_path):
    path = str(tmp_path / "legacy.sqlite3")
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE traces (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        connection.execute("INSERT INTO traces VALUES ('old', '{}')")
    store = TraceStore(path)
    assert await store.get("old") == {}
    await store.close()


def test_production_requires_certificate_validated_postgres(monkeypatch):
    monkeypatch.setenv("SOWCAST_ENV", "production")
    for location in (
        "local.sqlite3",
        "postgresql+asyncpg://user@localhost/db",
        "postgresql+asyncpg://user@localhost/db?sslmode=disable",
    ):
        with pytest.raises(ValueError):
            Database(location)
    database = Database("postgresql+asyncpg://user@localhost/db?sslmode=require")
    assert database.sqlite is False
    assert "sslmode" not in database.engine.url.query
    monkeypatch.delenv("SOWCAST_ENV")
    with pytest.raises(ValueError, match="persistent file"):
        Database("sqlite+aiosqlite:///:memory:")


def test_bounded_redaction_handles_embedded_credentials():
    from sowcast.storage.traces import redact

    value = redact(
        {
            "nested": {"authorization": "private"},
            "message": "https://user:secret@example.org/?api-key=private Bearer hidden",
        }
    )
    encoded = json.dumps(value)
    assert "private" not in encoded and "hidden" not in encoded and "user:secret" not in encoded


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["refused", "timeout", "authentication", "tls"])
async def test_connection_failures_are_translated_without_private_details(
    kind, tmp_path, monkeypatch
):
    import ssl
    from contextlib import asynccontextmanager

    from asyncpg.exceptions import InvalidPasswordError

    from sowcast.storage.errors import StorageUnavailable

    errors = {
        "refused": ConnectionRefusedError,
        "timeout": TimeoutError,
        "authentication": InvalidPasswordError,
        "tls": ssl.SSLError,
    }
    database = Database(str(tmp_path / "fail.sqlite3"))

    @asynccontextmanager
    async def unavailable(engine):
        raise errors[kind]("private connection details")
        yield

    monkeypatch.setattr(type(database.engine), "begin", unavailable)
    with pytest.raises(StorageUnavailable, match="Storage is unavailable") as caught:
        await database.ready()
    assert "private" not in str(caught.value)
    await database.close()


@pytest.mark.asyncio
async def test_programming_errors_are_not_relabelled(tmp_path):
    database = Database(str(tmp_path / "valid.sqlite3"))
    with pytest.raises(ValueError, match="programming error"):
        async with database.transaction():
            raise ValueError("programming error")
    await database.close()
