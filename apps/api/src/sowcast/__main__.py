import argparse
import asyncio
import os
from uuid import uuid4

import httpx
from pydantic import ValidationError

from sowcast.cache.forecast import ForecastCache
from sowcast.sources.forecast import ForecastClient
from sowcast.sources.models import Location, SourceError
from sowcast.sources.services import SourceServices
from sowcast.sources.transport import SourceTransport
from sowcast.storage.database import Database


async def run(latitude: float, longitude: float) -> None:
    location = Location(latitude=latitude, longitude=longitude)
    async with httpx.AsyncClient() as http:
        source = ForecastClient(SourceTransport(http))
        cache = ForecastCache(source.fetch)
        try:
            result = await cache.get(location)
            print(result.model_dump_json(indent=2))
        except SourceError as exc:
            print(exc.envelope(str(uuid4())).model_dump_json())
            raise SystemExit(1) from exc
        finally:
            await cache.close()


async def run_backtest(latitude: float, longitude: float) -> None:
    location = Location(latitude=latitude, longitude=longitude)
    async with httpx.AsyncClient() as http:
        services = SourceServices(http, os.environ.get("DATA_GOV_IN_API_KEY"))
        try:
            result = await services.backtest.get(location)
            print(result.model_dump_json(indent=2))
        except SourceError as exc:
            print(exc.envelope(str(uuid4())).model_dump_json())
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
    parser = argparse.ArgumentParser(description="Fetch live Sowcast weather evidence")
    parser.add_argument(
        "command", nargs="?", choices=("weather", "backtest", "migrate", "serve"), default="weather"
    )
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Run one deduplicated backtest for an external scheduler",
    )
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "sowcast.api.app:app",
            host="0.0.0.0",
            port=int(os.environ.get("PORT", "8000")),
            proxy_headers=False,
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
