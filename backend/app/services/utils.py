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


"""Magic-number validation for document uploads.

Browsers report whatever mime the OS extension mapping says, and the
extension itself is user-controlled, so neither can be trusted. A renamed
executable or html file must not land in the documents bucket just because
it ends in .pdf. We sniff the first bytes of the upload and only accept
files whose content actually matches a supported format.

Only the formats the documents endpoint accepts are recognized:
PDF, JPEG, PNG, WebP, and HEIC/HEIF (phone photos).
"""

from __future__ import annotations

# Brands that identify HEIC/HEIF inside an ISO Base Media File Format
# container. The brand sits at bytes 8-12, after the box size and "ftyp".
_HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs"}
_HEIF_BRANDS = {b"mif1", b"msf1", b"heif"}

# Read at least this many bytes from the upload before calling sniff_mime;
# the WebP and HEIC checks need bytes beyond the first four.
HEADER_LENGTH = 16


def sniff_mime(header_bytes: bytes) -> str | None:
    """Identify a supported document format from its leading bytes.

    Returns the canonical mime type for PDF, JPEG, PNG, WebP, HEIC, or HEIF,
    or None when the bytes match none of them. Pass at least HEADER_LENGTH
    bytes; shorter inputs simply fail the longer signatures.
    """
    if not header_bytes:
        return None

    if header_bytes.startswith(b"%PDF-"):
        return "application/pdf"
    if header_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    # WebP: RIFF container with the WEBP fourcc at bytes 8-12.
    if header_bytes.startswith(b"RIFF") and header_bytes[8:12] == b"WEBP":
        return "image/webp"
    # HEIC/HEIF: ISO BMFF "ftyp" box at bytes 4-8, brand at bytes 8-12.
    if header_bytes[4:8] == b"ftyp":
        brand = header_bytes[8:12]
        if brand in _HEIC_BRANDS:
            return "image/heic"
        if brand in _HEIF_BRANDS:
            return "image/heif"
    return None


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
