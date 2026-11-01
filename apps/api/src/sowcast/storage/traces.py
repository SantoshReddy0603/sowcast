import hashlib
import hmac
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

    async def save(
        self, identifier: str, trace: dict[str, Any], access_token: str | None = None
    ) -> None:
        body = redact(trace)
        if access_token is not None:
            body = {
                "trace": body,
                "access_digest": hashlib.sha256(access_token.encode()).hexdigest(),
            }
        encoded = json.dumps(body, ensure_ascii=False)
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
            return self._summary(row.body) if row else None

    @staticmethod
    def _summary(body: str) -> dict[str, Any]:
        raw: dict[str, Any] = json.loads(body)
        if "access_digest" in raw and isinstance(raw.get("trace"), dict):
            return dict(raw["trace"])
        return raw

    @staticmethod
    def _authorized(body: str, access_token: str | None) -> bool:
        if not access_token or len(access_token) > 128:
            return False
        raw: dict[str, Any] = json.loads(body)
        digest = raw.get("access_digest")
        return isinstance(digest, str) and hmac.compare_digest(
            digest, hashlib.sha256(access_token.encode()).hexdigest()
        )

    async def get_authorized(
        self, identifier: str, access_token: str | None
    ) -> dict[str, Any] | None:
        async with self.database.transaction() as session:
            row = await session.get(AgentTrace, identifier)
            if row is None or not self._authorized(row.body, access_token):
                return None
            return self._summary(row.body)

    async def delete_authorized(self, identifier: str, access_token: str | None) -> bool:
        async with self.database.transaction(write=True) as session:
            row = await session.get(AgentTrace, identifier)
            if row is None or not self._authorized(row.body, access_token):
                return False
            await session.delete(row)
            return True

    async def close(self) -> None:
        if self.owns_database:
            await self.database.close()
