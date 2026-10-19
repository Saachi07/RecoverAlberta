"""AI firewall for untrusted document text flowing into Gemini prompts.

The canonical implementation lives in the repo-root ``pdf_and_summary``
package (stdlib-only, so it stays importable from both the backend and the
standalone CLI). This module re-exports it on the backend's import path so
services and blueprints can do ``from ..services.ai_guard import ...``.

See ``pdf_and_summary/ai_guard.py`` for the full design notes: sanitize
document text before it reaches a prompt, pass it inside clearly delimited
untrusted blocks, and post-validate model output (html stripping, unknown
URL removal, length caps) before persisting or rendering it.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Put the repo root (parent of ``backend``) on sys.path so ``pdf_and_summary``
# is importable. parents: [0]=services [1]=app [2]=backend [3]=repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pdf_and_summary.ai_guard import (  # noqa: E402  (path setup must run first)
    MAX_STRING_LENGTH,
    UNTRUSTED_BLOCK_CLOSE,
    UNTRUSTED_BLOCK_OPEN,
    contains_injection,
    sanitize_for_prompt,
    validate_model_output,
    wrap_untrusted,
)

__all__ = [
    "MAX_STRING_LENGTH",
    "UNTRUSTED_BLOCK_CLOSE",
    "UNTRUSTED_BLOCK_OPEN",
    "contains_injection",
    "sanitize_for_prompt",
    "validate_model_output",
    "wrap_untrusted",
]
