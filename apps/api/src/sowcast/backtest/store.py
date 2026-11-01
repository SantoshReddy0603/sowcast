import time

from sqlalchemy import delete, func, select

from sowcast.backtest.metrics import BacktestResult
from sowcast.storage.database import Database
from sowcast.storage.models import BacktestJob, BacktestRecord


class BacktestStore:
    def __init__(self, location: str | Database) -> None:
        self.database = location if isinstance(location, Database) else Database(location)
        self.owns_database = not isinstance(location, Database)

    async def lookup(self, key: str) -> BacktestResult | None:
        async with self.database.transaction() as session:
            row = await session.get(BacktestRecord, key)
            if row and 0 <= time.time() - row.saved < 86400:
                return BacktestResult.model_validate_json(row.body)
        return None

    async def claim(self, key: str, owner: str) -> BacktestResult | bool:
        now = time.time()
        async with self.database.transaction(write=True) as session:
            row = await session.get(BacktestRecord, key)
            if row and 0 <= now - row.saved < 86400:
                return BacktestResult.model_validate_json(row.body)
            job = await session.get(BacktestJob, key)
            if job and job.expires > now:
                return False
            await session.execute(delete(BacktestJob).where(BacktestJob.expires <= now))
            count = await session.scalar(select(func.count()).select_from(BacktestJob))
            if count is not None and count >= 32:
                return False
            session.add(BacktestJob(key=key, owner=owner, expires=now + 300))
            return True

    async def finish(self, key: str, owner: str, result: BacktestResult) -> None:
        async with self.database.transaction(write=True) as session:
            job = await session.get(BacktestJob, key)
            if not job or job.owner != owner:
                return
            row = await session.get(BacktestRecord, key)
            if row:
                row.saved, row.body = time.time(), result.model_dump_json()
            else:
                session.add(
                    BacktestRecord(key=key, saved=time.time(), body=result.model_dump_json())
                )
            await session.delete(job)
            await session.flush()
            retained = (
                select(BacktestRecord.key)
                .order_by(BacktestRecord.saved.desc(), BacktestRecord.key)
                .limit(128)
            )
            await session.execute(delete(BacktestRecord).where(BacktestRecord.key.not_in(retained)))

    async def release(self, key: str, owner: str) -> None:
        async with self.database.transaction(write=True) as session:
            await session.execute(
                delete(BacktestJob).where(BacktestJob.key == key, BacktestJob.owner == owner)
            )

    async def close(self) -> None:
        if self.owns_database:
            await self.database.close()
