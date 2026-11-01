import asyncio
import random
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from sowcast.sources.models import SourceError, SourceHealth

QueryValue = str | int | float | list[str]


class SourceTransport:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        attempts: int = 3,
        failure_threshold: int = 3,
        cooldown: float = 30,
        source: str = "Open-Meteo forecast",
        timeout: float = 15,
        min_interval: float = 0,
        unavailable: bool = False,
    ) -> None:
        if attempts < 1 or failure_threshold < 1 or cooldown < 0:
            raise ValueError("Invalid resilience policy")
        self.client = client
        self.attempts = attempts
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self.health = SourceHealth()
        self.failures = 0
        self.opened_at: float | None = None
        self.lock = asyncio.Lock()
        self.source = source
        self.timeout = timeout
        self.request_count = 0
        self.min_interval = min_interval
        self.unavailable = unavailable
        self.last_started: float | None = None

    def report(self, status: str, code: str | None = None) -> None:
        self.health = SourceHealth.model_validate(
            {
                "status": status,
                "checked_at": datetime.now(UTC),
                "error_code": code,
                "request_count": self.request_count,
                "latency_ms": self.health.latency_ms,
            }
        )

    async def get(self, url: str, params: dict[str, QueryValue]) -> dict[str, Any]:
        if self.unavailable:
            self.report("unavailable", "source_unavailable")
            structlog.get_logger().info(
                "source_request",
                source=self.source,
                error_code="source_unavailable",
                latency_ms=0.0,
                attempt=0,
            )
            raise SourceError(
                "source_unavailable", "Source is disabled for this demonstration", True, self.source
            )
        async with self.lock:
            if self.opened_at is not None and time.monotonic() - self.opened_at < self.cooldown:
                structlog.get_logger().info(
                    "source_request",
                    source=self.source,
                    error_code="circuit_open",
                    latency_ms=0.0,
                    attempt=0,
                )
                raise SourceError(
                    "circuit_open", "Source is temporarily unavailable", True, self.source
                )
            for attempt in range(self.attempts):
                if self.last_started is not None:
                    remaining = self.min_interval - (time.monotonic() - self.last_started)
                    if remaining > 0:
                        await asyncio.sleep(remaining)
                started = time.monotonic()
                self.last_started = started
                self.request_count += 1
                try:
                    response = await self.client.get(
                        url,
                        params=params,
                        timeout=httpx.Timeout(self.timeout, connect=5),
                    )
                    if response.status_code >= 400:
                        raise SourceError(
                            f"http_{response.status_code}",
                            "Source rejected request",
                            response.status_code == 429 or response.status_code >= 500,
                        )
                    try:
                        payload: Any = response.json()
                    except ValueError as exc:
                        raise SourceError(
                            "invalid_response",
                            "Source returned invalid JSON",
                        ) from exc
                    if not isinstance(payload, dict):
                        raise SourceError("invalid_response", "Expected a source object")
                    self.failures = 0
                    self.opened_at = None
                    self.health = SourceHealth(
                        status="available",
                        checked_at=datetime.now(UTC),
                        request_count=self.request_count,
                        latency_ms=(time.monotonic() - started) * 1000,
                    )
                    structlog.get_logger().info(
                        "source_request",
                        source=self.source,
                        http_status=response.status_code,
                        latency_ms=round(self.health.latency_ms or 0.0, 3),
                        attempt=attempt + 1,
                    )
                    return payload
                except httpx.RequestError:
                    error = SourceError("network_error", "Source request failed", True, self.source)
                except SourceError as exc:
                    error = SourceError(exc.code, str(exc), exc.retryable, self.source)
                structlog.get_logger().info(
                    "source_request",
                    source=self.source,
                    error_code=error.code,
                    latency_ms=round((time.monotonic() - started) * 1000, 3),
                    attempt=attempt + 1,
                )
                if not error.retryable or attempt == self.attempts - 1:
                    self.failures += 1
                    if self.failures >= self.failure_threshold:
                        self.opened_at = time.monotonic()
                    self.health = SourceHealth(
                        status="unavailable",
                        checked_at=datetime.now(UTC),
                        error_code=error.code,
                        request_count=self.request_count,
                        latency_ms=(time.monotonic() - started) * 1000,
                    )
                    raise error
                await asyncio.sleep(random.uniform(0, min(2, 0.25 * 2**attempt)))
        raise RuntimeError("Unreachable retry state")
