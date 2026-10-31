import asyncio
import math
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable

from sowcast.sources.models import SourceError, SourceEvidence


class TTLCache[Key: Hashable, Value: SourceEvidence]:
    def __init__(
        self,
        fetch: Callable[[Key], Awaitable[Value]],
        *,
        ttl: float = 900,
        stale_for: float = 3600,
        capacity: int = 128,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not all(math.isfinite(v) and v >= 0 for v in (ttl, stale_for)) or capacity < 1:
            raise ValueError("Invalid cache policy")
        self.fetch = fetch
        self.ttl, self.stale_for, self.capacity = ttl, stale_for, capacity
        self.clock = clock
        self.entries: OrderedDict[Key, tuple[float, Value]] = OrderedDict()
        self.pending: dict[Key, asyncio.Task[Value]] = {}
        self.last_error: SourceError | None = None
        self.closed = False

    async def _refresh(self, key: Key) -> Value:
        try:
            value = await self.fetch(key)
            self.entries[key] = (self.clock(), value)
            self.entries.move_to_end(key)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
            self.last_error = None
            return value
        except SourceError as exc:
            self.last_error = exc
            raise
        finally:
            self.pending.pop(key, None)

    @staticmethod
    def _observe(task: asyncio.Task[Value]) -> None:
        if not task.cancelled():
            task.exception()

    async def get(self, key: Key) -> Value:
        if self.closed:
            raise RuntimeError("Cache is closed")
        now = self.clock()
        for old_key, (stored, _) in list(self.entries.items()):
            if now - stored >= self.ttl + self.stale_for:
                del self.entries[old_key]
        entry = self.entries.get(key)
        age = now - entry[0] if entry else math.inf
        if entry and age < self.ttl:
            self.entries.move_to_end(key)
            return entry[1].model_copy(deep=True)
        if key not in self.pending:
            if len(self.pending) >= self.capacity:
                if entry:
                    return entry[1].model_copy(update={"is_stale": True}, deep=True)
                raise SourceError(
                    "cache_busy",
                    "Concurrent source-request capacity reached",
                    True,
                    "Sowcast cache",
                )
            task = asyncio.create_task(self._refresh(key))
            task.add_done_callback(self._observe)
            self.pending[key] = task
        if entry:
            return entry[1].model_copy(update={"is_stale": True}, deep=True)
        return (await asyncio.shield(self.pending[key])).model_copy(deep=True)

    async def close(self) -> None:
        self.closed = True
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.entries.clear()
