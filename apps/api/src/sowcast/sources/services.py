import asyncio
import os
from datetime import date

import httpx

from sowcast.backtest.service import BacktestService
from sowcast.backtest.store import BacktestStore
from sowcast.cache.forecast import ForecastCache
from sowcast.cache.ttl import TTLCache
from sowcast.sources.flood import FloodClient, FloodEvidence
from sowcast.sources.forecast import ForecastClient
from sowcast.sources.geocoding import GeocodingClient, GeocodingEvidence
from sowcast.sources.history import HistoryClient
from sowcast.sources.mandi import MandiClient, MandiEvidence
from sowcast.sources.models import Location, SourceHealth
from sowcast.sources.power import PowerClient, PowerEvidence
from sowcast.sources.soil import SoilClient, SoilEvidence
from sowcast.sources.transport import SourceTransport
from sowcast.storage.database import Database


class SourceServices:
    def __init__(
        self, http: httpx.AsyncClient, agmarknet_key: str | None, database: Database | None = None
    ) -> None:
        names = {
            "open_meteo_forecast": "Open-Meteo forecast",
            "open_meteo_previous_runs": "Open-Meteo Previous Runs",
            "open_meteo_archive": "Open-Meteo ERA5 archive",
            "open_meteo_geocoding": "Open-Meteo geocoding",
            "open_meteo_flood": "Open-Meteo flood",
            "nasa_power": "NASA POWER",
            "soilgrids": "SoilGrids",
            "agmarknet": "Agmarknet",
        }
        disabled = os.environ.get("SOWCAST_UNAVAILABLE_SOURCE", "")
        if disabled and disabled not in names:
            raise ValueError("SOWCAST_UNAVAILABLE_SOURCE must be a configured source identifier")
        self.transports = {
            key: SourceTransport(
                http,
                source=name,
                min_interval=12 if key == "soilgrids" else 0,
                unavailable=key == disabled,
            )
            for key, name in names.items()
        }
        self.weather = ForecastCache(ForecastClient(self.transports["open_meteo_forecast"]).fetch)
        geocoding = GeocodingClient(self.transports["open_meteo_geocoding"])
        flood = FloodClient(self.transports["open_meteo_flood"])
        power = PowerClient(self.transports["nasa_power"])
        soil = SoilClient(self.transports["soilgrids"])
        mandi = MandiClient(self.transports["agmarknet"], agmarknet_key)

        async def search(key: tuple[str, str]) -> GeocodingEvidence:
            return await geocoding.fetch(*key)

        async def discharge(key: tuple[float, float]) -> FloodEvidence:
            return await flood.fetch(Location(latitude=key[0], longitude=key[1]))

        async def radiation(key: tuple[float, float, date, date]) -> PowerEvidence:
            return await power.fetch(Location(latitude=key[0], longitude=key[1]), key[2], key[3])

        async def properties(key: tuple[float, float]) -> SoilEvidence:
            return await soil.fetch(Location(latitude=key[0], longitude=key[1]))

        async def prices(key: tuple[str, str]) -> MandiEvidence:
            return await mandi.fetch(*key)

        self.backtest = BacktestService(
            HistoryClient(self.transports["open_meteo_previous_runs"]),
            HistoryClient(self.transports["open_meteo_archive"]),
            BacktestStore(
                database
                or os.environ.get("DATABASE_URL")
                or os.environ.get("SOWCAST_BACKTEST_DB", ".sowcast/backtest.sqlite3")
            ),
        )
        self.geocoding = TTLCache(search, ttl=86400, stale_for=86400)
        self.flood = TTLCache(discharge)
        self.power = TTLCache(radiation, ttl=86400, stale_for=86400)
        self.soil = TTLCache(properties, ttl=86400, stale_for=86400)
        self.mandi = TTLCache(prices, ttl=900, stale_for=3600)

    def health(self) -> dict[str, SourceHealth]:
        return {key: transport.health for key, transport in self.transports.items()}

    async def close(self) -> None:
        await asyncio.gather(
            self.weather.close(),
            self.backtest.close(),
            self.geocoding.close(),
            self.flood.close(),
            self.power.close(),
            self.soil.close(),
            self.mandi.close(),
        )
