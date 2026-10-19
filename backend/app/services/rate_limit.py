"""Tiny in-memory sliding-window rate limiter.

Protects the expensive Gemini-backed endpoints (photo scans, document
analysis) from runaway clients burning the shared API quota. Per-process
only: each worker keeps its own counters, so the effective limit scales
with worker count. That is acceptable for the current single-process
deployment; swap in a shared store (Redis, Postgres) if the app ever runs
behind multiple workers and the limits need to be exact.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_WINDOW_SECONDS = 60.0

_lock = threading.Lock()
_events: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def check_rate_limit(user_id: str, key: str, max_per_minute: int) -> bool:
    """Record one event for (user_id, key) and report whether the caller is
    within the limit. Returns False when the user has already made
    max_per_minute calls in the past 60 seconds; the event is not recorded
    in that case, so blocked retries do not extend the lockout."""
    now = time.monotonic()
    bucket_key = (str(user_id), key)
    with _lock:
        bucket = _events[bucket_key]
        while bucket and now - bucket[0] > _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= max_per_minute:
            return False
        bucket.append(now)
        return True


def reset() -> None:
    """Clear all counters. Used by tests so runs do not leak into each other."""
    with _lock:
        _events.clear()
