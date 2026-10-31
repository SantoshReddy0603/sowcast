import asyncio
import os
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

from alembic import command
from alembic.config import Config
from asyncpg.exceptions import PostgresError
from sqlalchemy import Connection, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from sowcast.storage.errors import StorageUnavailable

STORAGE_FAILURES = (SQLAlchemyError, PostgresError, OSError, TimeoutError)

MIGRATION_LOCKS: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()


class Database:
    def __init__(self, location: str) -> None:
        if "://" not in location:
            Path(location).parent.mkdir(parents=True, exist_ok=True)
            location = "sqlite+aiosqlite:///" + str(Path(location).resolve()).replace("\\", "/")
        location = location.replace("postgres://", "postgresql+asyncpg://", 1)
        location = location.replace("postgresql://", "postgresql+asyncpg://", 1)
        if not location.startswith(("sqlite+aiosqlite://", "postgresql+asyncpg://")):
            raise ValueError("Use SQLite/aiosqlite or PostgreSQL/asyncpg")
        self.sqlite = location.startswith("sqlite")
        if os.environ.get("SOWCAST_ENV") == "production" and (
            self.sqlite or "sslmode=" not in location
        ):
            raise ValueError("Production storage requires PostgreSQL with an explicit TLS mode")
        url = make_url(location)
        if self.sqlite and url.database in {None, "", ":memory:"}:
            raise ValueError("SQLite storage requires a persistent file path")
        connect_args: dict[str, Any] = (
            {"timeout": 10} if self.sqlite else {"timeout": 10, "command_timeout": 15}
        )
        if not self.sqlite and "sslmode" in url.query:
            mode = url.query["sslmode"]
            if mode not in {"require", "verify-full", "verify-ca", "disable"}:
                raise ValueError("Unsupported PostgreSQL SSL mode")
            if mode == "disable" and os.environ.get("SOWCAST_ENV") == "production":
                raise ValueError("Production PostgreSQL requires TLS")
            if mode != "disable":
                connect_args["ssl"] = ssl.create_default_context()
            url = url.difference_update_query(["sslmode"])
        self.engine = create_async_engine(
            url,
            poolclass=NullPool,
            hide_parameters=True,
            connect_args=connect_args,
        )
        self.initialized = False
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        try:
            await self._initialize()
        except STORAGE_FAILURES:
            raise StorageUnavailable("Storage is unavailable; retry later.") from None

    async def _initialize(self) -> None:
        async with self.lock:
            if self.initialized:
                return
            migration_lock = MIGRATION_LOCKS.setdefault(asyncio.get_running_loop(), asyncio.Lock())
            async with migration_lock, self.engine.begin() as connection:
                await connection.execute(
                    text(
                        "BEGIN IMMEDIATE" if self.sqlite else "SELECT pg_advisory_xact_lock(482030)"
                    )
                )

                def upgrade(sync_connection: Connection) -> None:
                    config = Config()
                    config.set_main_option(
                        "script_location", str(Path(__file__).parent / "migrations")
                    )
                    config.attributes["connection"] = sync_connection
                    command.upgrade(config, "head")

                await connection.run_sync(upgrade)
            self.initialized = True

    @asynccontextmanager
    async def transaction(self, *, write: bool = False) -> AsyncIterator[AsyncSession]:
        await self.initialize()
        try:
            async with AsyncSession(self.engine) as session, session.begin():
                if write:
                    await session.execute(
                        text(
                            "BEGIN IMMEDIATE"
                            if self.sqlite
                            else "SELECT pg_advisory_xact_lock(482031)"
                        )
                    )
                yield session
        except STORAGE_FAILURES:
            raise StorageUnavailable("Storage is unavailable; retry later.") from None

    async def ready(self) -> None:
        async with self.transaction() as session:
            await session.execute(text("SELECT 1"))

    async def close(self) -> None:
        await self.engine.dispose()
