"""Live updates (vehicle positions) fan out to the web clients through per-company channels.

Publishing is synchronous (called from request handlers); listening is asynchronous, so an open live map holds
no worker thread. Redis pub/sub in production (the API runs several processes); an in-process broker for
development and tests. A subscriber only ever receives the channels of the companies in its scope.
"""

import asyncio
import json
import threading
from collections.abc import AsyncIterator, Iterable
from functools import lru_cache

from app.core.config import get_settings

PREFIX = "live:company:"


def channel(company_id: int) -> str:
    return f"{PREFIX}{company_id}"


def _offer(q: asyncio.Queue, data: str) -> None:
    if not q.full():  # a client that stopped reading loses updates, never blocks the publisher
        q.put_nowait(data)


class MemoryBroker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}

    def publish(self, company_id: int, message: dict) -> None:
        data = json.dumps(message, default=str)
        with self._lock:
            targets = list(self._subscribers.get(channel(company_id), ()))
        for loop, q in targets:
            loop.call_soon_threadsafe(_offer, q, data)

    async def listen(self, company_ids: Iterable[int], timeout: float) -> AsyncIterator[str | None]:
        """Yields messages; yields None every `timeout` seconds without one (keep-alive)."""
        entry = (asyncio.get_running_loop(), asyncio.Queue(maxsize=1000))
        names = [channel(c) for c in company_ids]
        with self._lock:
            for name in names:
                self._subscribers.setdefault(name, set()).add(entry)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(entry[1].get(), timeout)
                except TimeoutError:
                    yield None
        finally:
            with self._lock:
                for name in names:
                    self._subscribers.get(name, set()).discard(entry)


class RedisBroker:
    def __init__(self, url: str) -> None:
        import redis

        self._url = url
        self._redis = redis.Redis.from_url(url)

    def publish(self, company_id: int, message: dict) -> None:
        self._redis.publish(channel(company_id), json.dumps(message, default=str))

    async def listen(self, company_ids: Iterable[int], timeout: float) -> AsyncIterator[str | None]:
        import redis.asyncio as aioredis

        client = aioredis.Redis.from_url(self._url)
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(*[channel(c) for c in company_ids])
        try:
            while True:
                msg = await pubsub.get_message(timeout=timeout)
                yield None if msg is None else msg["data"].decode()
        finally:
            await pubsub.aclose()
            await client.aclose()


@lru_cache
def broker() -> MemoryBroker | RedisBroker:
    settings = get_settings()
    # the in-process broker cannot reach the other API worker processes: production always uses Redis
    use_redis = settings.is_production or settings.live_broker == "redis"
    return RedisBroker(settings.cache_redis_url) if use_redis else MemoryBroker()
