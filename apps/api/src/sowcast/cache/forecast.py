import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from sowcast.cache.ttl import TTLCache
from sowcast.sources.models import Forecast, Location, SourceError


class ForecastCache:
    def __init__(
        self,
        fetch: Callable[[Location], Awaitable[Forecast]],
        *,
        ttl: float = 900,
        stale_for: float = 3600,
        capacity: int = 128,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        async def load(key: tuple[float, float]) -> Forecast:
            return await fetch(Location(latitude=key[0], longitude=key[1]))

        self.cache = TTLCache(load, ttl=ttl, stale_for=stale_for, capacity=capacity, clock=clock)

    @property
    def entries(self) -> OrderedDict[tuple[float, float], tuple[float, Forecast]]:
        return self.cache.entries

    @property
    def pending(self) -> dict[tuple[float, float], asyncio.Task[Forecast]]:
        return self.cache.pending

    @property
    def last_error(self) -> SourceError | None:
        return self.cache.last_error

    async def get(self, location: Location) -> Forecast:
        return await self.cache.get((location.latitude, location.longitude))

    async def close(self) -> None:
        await self.cache.close()
