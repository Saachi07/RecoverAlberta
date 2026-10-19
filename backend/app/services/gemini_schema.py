"""Convert a Pydantic model into a Gemini-compatible response schema.

google-genai 0.3.0 (pinned for httpx<0.28 / Supabase compatibility) does not
dereference the ``$ref``/``$defs`` that Pydantic emits for nested models, and
its Google AI (non-Vertex) schema path rejects JSON-schema keys like ``title``
and ``default``. This helper inlines all ``$ref`` targets, drops the
unsupported keys, and collapses ``Optional[T]`` (``anyOf: [T, null]``) into a
nullable field, producing a plain dict the SDK accepts.
"""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel

# JSON-schema keys google-genai 0.3.0 rejects in Google AI mode.
_DROP_KEYS = {"title", "default", "additionalProperties", "$defs"}


def _deref(node: Any, defs: dict) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].split("/")[-1]
            return _deref(copy.deepcopy(defs[name]), defs)
        # Collapse Optional[T] (anyOf with a null branch) into nullable T.
        if "anyOf" in node:
            variants = [v for v in node["anyOf"] if v.get("type") != "null"]
            nullable = any(v.get("type") == "null" for v in node["anyOf"])
            if len(variants) == 1:
                merged = _deref(copy.deepcopy(variants[0]), defs)
                if nullable:
                    merged["nullable"] = True
                for key, value in node.items():
                    if key != "anyOf" and key not in _DROP_KEYS:
                        merged.setdefault(key, _deref(value, defs))
                return merged
        return {k: _deref(v, defs) for k, v in node.items() if k not in _DROP_KEYS}
    if isinstance(node, list):
        return [_deref(v, defs) for v in node]
    return node


def to_gemini_schema(model: type[BaseModel]) -> dict:
    """Return a dereferenced, Gemini-safe JSON schema dict for ``model``."""
    schema = model.model_json_schema()
    return _deref(schema, schema.get("$defs", {}))
