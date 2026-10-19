"""Opt-in pagination for list endpoints.

A list call with no ``limit`` query param behaves exactly as before and returns
everything, so existing callers (the Inventory page computes whole-inventory
totals, the recommender reads every item) keep working untouched. A caller that
passes ``limit`` gets a bounded page plus a ``total`` count for building pagers.

This is a pure helper so it is unit-testable without a database.
"""

from __future__ import annotations

from typing import Optional

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def parse_pagination(args) -> tuple[Optional[int], int]:
    """Read ``limit`` / ``offset`` from a request args mapping.

    Returns ``(limit, offset)``. ``limit`` is ``None`` when the caller did not
    ask to paginate (meaning "return all"); otherwise it is clamped to
    [1, MAX_LIMIT]. ``offset`` is clamped to >= 0. Bad values fall back to
    sensible defaults rather than erroring, so a malformed query never 500s.
    """
    raw_limit = args.get("limit")
    if raw_limit is None or raw_limit == "":
        return None, 0

    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))

    try:
        offset = max(0, int(args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0

    return limit, offset
