import math
import os
import threading
import time
from collections import deque
from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from sowcast.sources.models import ErrorDetail, ErrorEnvelope


def setting(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if not 1 <= value <= 10000:
        raise ValueError(f"{name} must be an integer from 1 to 10000")
    return value


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.window = 60
        self.general = setting("SOWCAST_RATE_LIMIT", 120)
        self.agent = setting("SOWCAST_AGENT_LIMIT", 10)
        self.backtest = setting("SOWCAST_BACKTEST_LIMIT", 5)
        self.agent_total = setting("SOWCAST_AGENT_GLOBAL_LIMIT", 10)
        self.backtest_total = setting("SOWCAST_BACKTEST_GLOBAL_LIMIT", 10)
        self.events: dict[tuple[str, str], deque[float]] = {}
        self.lock = threading.Lock()

    def check(self, client: str, path: str) -> int | None:
        policies = [(client, "api", self.general)]
        if path.rstrip("/") in {"/v1/plans", "/v1/chat"}:
            policies += [(client, "agent", self.agent), ("", "agent_total", self.agent_total)]
        if path.rstrip("/") == "/v1/backtests":
            policies += [
                (client, "backtest", self.backtest),
                ("", "backtest_total", self.backtest_total),
            ]
        with self.lock:
            now = self.clock()
            for key in tuple(self.events):
                events = self.events[key]
                while events and events[0] <= now - self.window:
                    events.popleft()
                if not events:
                    del self.events[key]
            keys = [(host, bucket) for host, bucket, _ in policies]
            if len(self.events) + sum(key not in self.events for key in keys) > 4096:
                return self.window
            for host, bucket, limit in policies:
                bucket_events = self.events.get((host, bucket))
                if bucket_events and len(bucket_events) >= limit:
                    return max(1, math.ceil(bucket_events[0] + self.window - now))
            for key in keys:
                self.events.setdefault(key, deque()).append(now)
        return None


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, limiter: RateLimiter) -> None:
        self.app, self.limiter = app, limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] != "OPTIONS" and scope["path"] != "/health":
            request = Request(scope)
            retry = self.limiter.check(
                request.client.host if request.client else "unknown", scope["path"]
            )
            if retry is not None:
                body = ErrorEnvelope(
                    error=ErrorDetail(
                        code="rate_limited",
                        message="Request limit reached; retry after the indicated delay.",
                        source="Sowcast API",
                        retryable=True,
                        request_id=request.state.request_id,
                    )
                )
                response = JSONResponse(
                    body.model_dump(), status_code=429, headers={"Retry-After": str(retry)}
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
