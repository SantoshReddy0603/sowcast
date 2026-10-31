import json
import re
import time
from typing import Any

from sqlalchemy import delete, select

from sowcast.storage.database import Database
from sowcast.storage.models import AgentTrace

SECRET = re.compile(r"(?i)(api[-_]?key|authorization|password|secret|token)")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if SECRET.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(
            r"(?i)(api[-_]?key|token|password|secret|authorization)\s*[:=]\s*(?:Bearer\s+)?([^&\s]+)",
            r"\1=[redacted]",
            value,
        )
        value = re.sub(r"(?i)Bearer\s+[^\s,]+", "Bearer [redacted]", value)
        return re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[redacted]@", value)[:2000]
    return value


class TraceStore:
    def __init__(self, location: str | Database) -> None:
        self.database = location if isinstance(location, Database) else Database(location)
        self.owns_database = not isinstance(location, Database)

    async def save(self, identifier: str, trace: dict[str, Any]) -> None:
        encoded = json.dumps(redact(trace), ensure_ascii=False)
        if len(encoded.encode()) > 64000:
            raise ValueError("Trace exceeds storage limit")
        async with self.database.transaction(write=True) as session:
            row = await session.get(AgentTrace, identifier)
            if row:
                row.body, row.saved = encoded, time.time()
            else:
                session.add(AgentTrace(id=identifier, body=encoded, saved=time.time()))
            await session.flush()
            retained = (
                select(AgentTrace.id)
                .order_by(AgentTrace.saved.desc(), AgentTrace.id.desc())
                .limit(1000)
            )
            await session.execute(delete(AgentTrace).where(AgentTrace.id.not_in(retained)))

    async def get(self, identifier: str) -> dict[str, Any] | None:
        async with self.database.transaction() as session:
            row = await session.get(AgentTrace, identifier)
            return json.loads(row.body) if row else None

    async def close(self) -> None:
        if self.owns_database:
            await self.database.close()
