"""Bounded in-memory caches. This is the only "storage" LotusLab has."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from typing import Generic, TypeVar

V = TypeVar("V")


@dataclass(slots=True)
class Entry(Generic[V]):
    value: V
    stored_at: float
    ttl_s: float

    def age(self, now: float) -> float:
        return now - self.stored_at

    def fresh(self, now: float) -> bool:
        return self.age(now) < self.ttl_s


class LRUCache(Generic[V]):
    """Least-recently-used map with a hard size bound. O(1) get / put."""

    def __init__(self, max_entries: int) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._data: OrderedDict[Hashable, V] = OrderedDict()
        self.max_entries = max_entries
        self.hits = 0
        self.misses = 0

    def get(self, key: Hashable) -> V | None:
        try:
            self._data.move_to_end(key)
        except KeyError:
            self.misses += 1
            return None
        self.hits += 1
        return self._data[key]

    def put(self, key: Hashable, value: V) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)

    def stats(self) -> dict[str, int]:
        return {"entries": len(self), "max_entries": self.max_entries, "hits": self.hits, "misses": self.misses}


class TTLCache(Generic[V]):
    """LRU + per-entry TTL + single-flight loading + stale-if-error.

    * Concurrent requests for the same missing key share one in-flight load.
    * When a load fails and an expired entry younger than ``stale_grace_s`` exists,
      that entry is returned and flagged stale instead of failing the request.
    """

    def __init__(self, max_entries: int, stale_grace_s: float, clock: Callable[[], float] = time.time) -> None:
        self._lru: LRUCache[Entry[V]] = LRUCache(max_entries)
        self._inflight: dict[Hashable, asyncio.Future[Entry[V]]] = {}
        self.stale_grace_s = stale_grace_s
        self.clock = clock
        self.coalesced = 0
        self.stale_served = 0

    async def get_or_load(
        self, key: Hashable, loader: Callable[[], Awaitable[V]], ttl_s: float
    ) -> tuple[Entry[V], str]:
        """Return ``(entry, status)`` where status is ``hit``, ``miss`` or ``stale``."""
        now = self.clock()
        entry = self._lru.get(key)
        if entry is not None and entry.fresh(now):
            return entry, "hit"

        pending = self._inflight.get(key)
        if pending is not None:
            self.coalesced += 1
            return await asyncio.shield(pending), "hit"

        fut: asyncio.Future[Entry[V]] = asyncio.get_running_loop().create_future()
        self._inflight[key] = fut
        try:
            value = await loader()
        except Exception as exc:
            if entry is not None and entry.age(now) < entry.ttl_s + self.stale_grace_s:
                self.stale_served += 1
                fut.set_result(entry)
                return entry, "stale"
            fut.set_exception(exc)
            fut.exception()  # mark retrieved so asyncio does not warn when nobody waits
            raise
        else:
            fresh = Entry(value, self.clock(), ttl_s)
            self._lru.put(key, fresh)
            fut.set_result(fresh)
            return fresh, "miss"
        finally:
            self._inflight.pop(key, None)

    def stats(self) -> dict[str, int]:
        return {**self._lru.stats(), "coalesced": self.coalesced, "stale_served": self.stale_served}
