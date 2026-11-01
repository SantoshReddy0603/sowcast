from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

import httpx

from sowcast.sources.models import SourceError, SourceEvidence
from sowcast.sources.transport import QueryValue, SourceTransport

Result = TypeVar("Result", bound=SourceEvidence)


class SourceClientBase:
    def __init__(self, transport: SourceTransport) -> None:
        self.transport = transport

    async def request(
        self,
        url: str,
        params: dict[str, QueryValue],
        parse: Callable[[dict[str, Any]], Result],
    ) -> Result:
        payload = await self.transport.get(url, params)
        try:
            result = parse(payload)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError) as exc:
            self.transport.report("degraded", "invalid_response")
            raise SourceError(
                "invalid_response",
                "Source schema or units are invalid",
                False,
                self.transport.source,
            ) from exc
        if result.data_status != "complete":
            self.transport.report("degraded", f"{result.data_status}_data")
        return result


def metadata(
    source: str,
    url: str,
    params: dict[str, QueryValue],
    attribution: str,
    attribution_url: str,
    licence_url: str | None,
    modifications: str,
) -> dict[str, Any]:
    public_params = {key: value for key, value in params.items() if key != "api-key"}
    return {
        "source": source,
        "request_url": str(httpx.Request("GET", url, params=public_params).url),
        "fetched_at": datetime.now(UTC),
        "attribution_text": attribution,
        "attribution_url": attribution_url,
        "licence_url": licence_url,
        "modifications": modifications,
    }
