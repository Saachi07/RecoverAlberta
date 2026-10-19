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
