import argparse
import asyncio
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

import httpx
import structlog
from pydantic import ValidationError

from sowcast.cache.forecast import ForecastCache
from sowcast.configuration import load_environment
from sowcast.logging import configure_logging
from sowcast.sources.forecast import ForecastClient
from sowcast.sources.models import Location, SourceError
from sowcast.sources.services import SourceServices
from sowcast.sources.transport import SourceTransport
from sowcast.storage.backup import copy_database
from sowcast.storage.database import Database


async def run(latitude: float, longitude: float) -> None:
    identifier = str(uuid4())
    structlog.contextvars.bind_contextvars(request_id=identifier)
    location = Location(latitude=latitude, longitude=longitude)
    async with httpx.AsyncClient() as http:
        source = ForecastClient(SourceTransport(http))
        cache = ForecastCache(source.fetch)
        try:
            result = await cache.get(location)
            print(result.model_dump_json(indent=2))
        except SourceError as exc:
            print(exc.envelope(identifier).model_dump_json())
            raise SystemExit(1) from exc
        finally:
            await cache.close()


async def run_backtest(latitude: float, longitude: float) -> None:
    identifier = str(uuid4())
    structlog.contextvars.bind_contextvars(request_id=identifier)
    location = Location(latitude=latitude, longitude=longitude)
    async with httpx.AsyncClient() as http:
        services = SourceServices(http, os.environ.get("DATA_GOV_IN_API_KEY"))
        try:
            result = await services.backtest.get(location)
            print(result.model_dump_json(indent=2))
        except SourceError as exc:
            print(exc.envelope(identifier).model_dump_json())
            raise SystemExit(1) from exc
        finally:
            await services.close()


async def migrate() -> None:
    locations = (
        [os.environ["DATABASE_URL"]]
        if os.environ.get("DATABASE_URL")
        else [
            os.environ.get("SOWCAST_TRACE_DB", ".sowcast/traces.sqlite3"),
            os.environ.get("SOWCAST_BACKTEST_DB", ".sowcast/backtest.sqlite3"),
        ]
    )
    for location in locations:
        database = Database(location)
        try:
            await database.initialize()
        finally:
            await database.close()
    print('{"status":"migrated","revision":"0001"}')


def main() -> None:
    configure_logging()
    structlog.contextvars.bind_contextvars(request_id=str(uuid4()))
    parser = argparse.ArgumentParser(description="Fetch live Sowcast weather evidence")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("weather", "backtest", "migrate", "serve", "backup", "restore"),
        default="weather",
    )
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Run one deduplicated backtest for an external scheduler",
    )
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--source", type=Path, help="SQLite database or backup to read")
    parser.add_argument(
        "--destination", type=Path, help="New SQLite file; existing files are never overwritten"
    )
    parser.add_argument(
        "--env-file", type=Path, help="Load a local environment file before startup"
    )
    args = parser.parse_args()
    if args.command in {"backup", "restore"}:
        if args.source is None or args.destination is None:
            parser.error("Backup/restore requires --source and --destination")
        try:
            copy_database(args.source, args.destination)
        except (OSError, ValueError, sqlite3.Error):
            parser.error(
                "Cannot copy database: verify the source, parent folder and unused destination"
            )
        print("SQLite snapshot verified. Existing files were not overwritten.")
        return
    if args.env_file is not None:
        try:
            load_environment(args.env_file)
        except (OSError, UnicodeError, ValueError):
            parser.error("Cannot load environment file; check its path and KEY=value entries")
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "sowcast.api.app:app",
            host="0.0.0.0",
            port=int(os.environ.get("PORT", "8000")),
            proxy_headers=False,
            access_log=False,
        )
        return
    if args.command == "migrate":
        asyncio.run(migrate())
        return
    if args.latitude is None or args.longitude is None:
        parser.error("Latitude and longitude are required")
    try:
        Location(latitude=args.latitude, longitude=args.longitude)
    except ValidationError:
        parser.error("Coordinates must be finite: latitude -90 to 90, longitude -180 to 180")
    if args.scheduled and args.command != "backtest":
        parser.error("--scheduled requires the backtest command")
    asyncio.run(
        (run_backtest if args.command == "backtest" else run)(args.latitude, args.longitude)
    )


if __name__ == "__main__":
    main()
