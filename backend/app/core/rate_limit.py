"""Minimal in-process sliding-window rate limiter.

Suitable for a single-process local deployment; it keeps memory usage tiny and
needs no external service. Swap for Redis if the API is ever scaled out.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock

from fastapi import Request

from app.core.config import settings
from app.core.errors import RateLimitError


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                raise RateLimitError(
                    f"Too many requests. Please wait about {window_seconds} seconds and try again.",
                    code="rate_limited",
                )
            bucket.append(now)
            if len(self._hits) > 2048:  # keep the dict from growing forever
                for stale_key in [k for k, v in self._hits.items() if not v]:
                    self._hits.pop(stale_key, None)
            if len(bucket) == 0:
                self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_key(request: Request, scope: str, identity: str | None = None) -> str:
    who = identity or (request.client.host if request.client else "unknown")
    return f"{scope}:{who}"


def enforce(request: Request, scope: str, identity: str | None = None) -> None:
    limit, window = settings.rate_limit(scope)
    limiter.check(client_key(request, scope, identity), limit, window)
