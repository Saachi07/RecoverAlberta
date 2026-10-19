"""Shared Gemini call helper: transient-retry plus model fallback.

Gemini occasionally returns 503 UNAVAILABLE ("high demand") or 429
RESOURCE_EXHAUSTED under load. Those are transient, so we retry the primary
model a few times, then fall back to a second model once, before giving up
with ModelOverloaded. Non-transient errors propagate immediately.

This used to live only in gemini_inventory; the document and program-scraper
pipelines called Gemini with no retry at all, so a momentary outage failed
them outright. Centralizing it here keeps every Gemini call equally resilient.
"""

from __future__ import annotations

import time

PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-2.0-flash"
_TRANSIENT_MARKERS = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "overloaded", "high demand")


class ModelOverloaded(RuntimeError):
    """Raised when Gemini stays unavailable after retries; maps to HTTP 503."""


def _is_transient(exc: Exception) -> bool:
    return any(marker in str(exc) for marker in _TRANSIENT_MARKERS)


def generate_with_retry(
    client,
    contents,
    config,
    *,
    model: str = PRIMARY_MODEL,
    fallback_model: str = FALLBACK_MODEL,
    attempts: int = 3,
):
    """Call Gemini, retrying the primary model on transient outages and then
    falling back to a second model once. Raises ModelOverloaded if it stays
    unavailable; re-raises any non-transient error immediately."""
    for attempt in range(attempts):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as exc:  # noqa: BLE001
            if not _is_transient(exc):
                raise
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))  # 1.5s, 3s

    # Primary stayed unavailable, try the fallback model once.
    try:
        return client.models.generate_content(model=fallback_model, contents=contents, config=config)
    except Exception as exc:  # noqa: BLE001
        if _is_transient(exc):
            raise ModelOverloaded(
                "Gemini is busy right now. Please try again in a moment."
            ) from exc
        raise
