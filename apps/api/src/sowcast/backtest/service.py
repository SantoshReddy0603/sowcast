import asyncio
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sowcast.backtest.metrics import BacktestResult, assess, uncertainty_note
from sowcast.backtest.store import BacktestStore
from sowcast.sources.history import HistoryClient
from sowcast.sources.models import Location, SourceError


class BacktestService:
    def __init__(
        self,
        previous: HistoryClient,
        archive: HistoryClient,
        store: BacktestStore,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.previous, self.archive, self.store, self.clock = previous, archive, store, clock
        self.pending: dict[str, asyncio.Task[BacktestResult]] = {}

    def window(self, location: Location) -> tuple[str, date]:
        end = self.clock().astimezone(UTC).date() - timedelta(days=6)
        key = json.dumps(
            [location.latitude, location.longitude, str(end), "1.1.0"], separators=(",", ":")
        )
        return key, end

    async def cached(self, location: Location) -> BacktestResult | None:
        result = await self.store.lookup(self.window(location)[0])
        if result is None:
            return None
        return result.model_copy(update={"uncertainty_note": uncertainty_note(result.scores)})

    async def get(self, location: Location) -> BacktestResult:
        key, end = self.window(location)
        if key not in self.pending:
            if len(self.pending) >= 32:
                raise SourceError(
                    "backtest_busy", "Backtest capacity reached", True, "Sowcast backtest"
                )
            task = asyncio.create_task(self._run(key, location, end))
            self.pending[key] = task
            task.add_done_callback(
                lambda completed: completed.exception() if not completed.cancelled() else None
            )
        return (await asyncio.shield(self.pending[key])).model_copy(deep=True)

    async def _run(self, key: str, location: Location, end: date) -> BacktestResult:
        owner = str(uuid4())
        claimed = False
        try:
            state = await self.store.claim(key, owner)
            if isinstance(state, BacktestResult):
                return state.model_copy(update={"uncertainty_note": uncertainty_note(state.scores)})
            if not state:
                raise SourceError(
                    "backtest_in_progress",
                    "A backtest job is already running or capacity is full",
                    True,
                    "Sowcast backtest",
                )
            claimed = True
            start = end - timedelta(days=59)
            async with asyncio.timeout(90):
                async with asyncio.TaskGroup() as group:
                    forecast_task = group.create_task(
                        self.previous.fetch(location, start, end, "previous")
                    )
                    reference_task = group.create_task(
                        self.archive.fetch(location, start, end, "archive")
                    )
                result = assess(
                    forecast_task.result(),
                    reference_task.result(),
                    start,
                    end,
                    self.clock().astimezone(UTC),
                )
                await self.store.finish(key, owner, result)
                return result
        except ExceptionGroup as exc:
            errors = exc.subgroup(SourceError)
            if errors:
                error = errors.exceptions[0]
                if isinstance(error, SourceError):
                    raise error from None
            raise SourceError(
                "backtest_failed", "Backtest source comparison failed", True, "Sowcast backtest"
            ) from None
        except TimeoutError:
            raise SourceError(
                "backtest_timeout", "Backtest exceeded its time budget", True, "Sowcast backtest"
            ) from None
        finally:
            if claimed:
                await self.store.release(key, owner)
            self.pending.pop(key, None)

    async def close(self) -> None:
        tasks = tuple(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.store.close()
