import asyncio
import json
from pathlib import Path

import httpx
import pytest

from sowcast.cache.ttl import TTLCache
from sowcast.sources.geocoding import GeocodingClient
from sowcast.sources.models import SourceError
from sowcast.sources.transport import SourceTransport


@pytest.mark.asyncio
async def test_stale_concurrency_hard_expiry_and_original_time():
    payload = json.loads(
        (Path(__file__).parent / "recorded/geocoding.json").read_text(encoding="utf-8")
    )
    now = [0.0]
    started = asyncio.Event()
    release = asyncio.Event()
    failing = False
    calls = 0

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as http:
        client = GeocodingClient(SourceTransport(http))

        async def fetch(key):
            nonlocal calls
            calls += 1
            if calls > 1:
                started.set()
                await release.wait()
            if failing:
                raise SourceError("network_error", "Source request failed", True)
            return await client.fetch(key)

        cache = TTLCache(fetch, ttl=10, stale_for=20, capacity=2, clock=lambda: now[0])
        original = await cache.get("Kolar")
        now[0] = 10
        stale = await asyncio.gather(*(cache.get("Kolar") for _ in range(20)))
        await started.wait()
        assert calls == 2
        assert all(item.is_stale and item.fetched_at == original.fetched_at for item in stale)
        failing = True
        release.set()
        await asyncio.gather(*cache.pending.values(), return_exceptions=True)
        assert cache.last_error.code == "network_error"
        now[0] = 30
        with pytest.raises(SourceError):
            await cache.get("Kolar")
        assert "Kolar" not in cache.entries
        assert not cache.pending
        await cache.close()


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_cancel_shared_fetch():
    payload = json.loads(
        (Path(__file__).parent / "recorded/geocoding.json").read_text(encoding="utf-8")
    )
    release = asyncio.Event()
    entered = asyncio.Event()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as http:
        client = GeocodingClient(SourceTransport(http))

        async def fetch(key):
            entered.set()
            await release.wait()
            return await client.fetch(key)

        cache = TTLCache(fetch)
        first = asyncio.create_task(cache.get("Kolar"))
        await entered.wait()
        second = asyncio.create_task(cache.get("Kolar"))
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert (await second).places
        assert not cache.pending
        await cache.close()
        with pytest.raises(RuntimeError):
            await cache.get("Kolar")


@pytest.mark.asyncio
async def test_stale_available_when_refresh_capacity_is_busy():
    payload = json.loads(
        (Path(__file__).parent / "recorded/geocoding.json").read_text(encoding="utf-8")
    )
    release = asyncio.Event()
    entered = asyncio.Event()
    now = [0.0]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as http:
        client = GeocodingClient(SourceTransport(http))

        async def fetch(key):
            if key == "Bengaluru":
                entered.set()
                await release.wait()
            return await client.fetch(key)

        cache = TTLCache(fetch, ttl=1, stale_for=20, capacity=1, clock=lambda: now[0])
        original = await cache.get("Kolar")
        now[0] = 2
        pending = asyncio.create_task(cache.get("Bengaluru"))
        await entered.wait()
        stale = await cache.get("Kolar")
        assert stale.is_stale
        assert stale.fetched_at == original.fetched_at
        release.set()
        await pending
        await cache.close()
