"""In-process sliding-window rate limiter for sensitive endpoints.

This protects authentication endpoints from brute force on a single worker.
For multi-worker or multi-host deployments, enforce limits at the reverse
proxy / API gateway as well (see docs/OPERATIONS.md) because this state is
not shared between processes.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, scope: str, key: str) -> bool:
        """Record a hit; return False when the caller is over the limit."""
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[(scope, key)]
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def _limiter():
    from app.config import settings
    global auth_rate_limiter
    if auth_rate_limiter is None:
        auth_rate_limiter = SlidingWindowRateLimiter(settings.rate_limit_auth_per_minute)
    return auth_rate_limiter


auth_rate_limiter: SlidingWindowRateLimiter | None = None


def rate_limit(scope: str):
    """FastAPI dependency enforcing the auth rate limit per client IP."""

    async def dependency(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        if not _limiter().hit(scope, ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please wait and try again.",
                headers={"Retry-After": "60"},
            )

    return dependency
