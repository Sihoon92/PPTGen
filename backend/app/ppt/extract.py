"""Robust JSON extraction from small-model output.

``gemma3n:e4b`` rarely emits clean JSON: it wraps output in markdown fences, adds
prose before/after, and leaves trailing commas. ``extract_json`` recovers the first
balanced JSON value and tolerates the common failure modes before giving up.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


class JsonExtractError(ValueError):
    """Raised when no valid JSON value can be recovered from model text."""


def _strip_fences(text: str) -> str:
    m = _FENCE.search(text)
    return m.group(1) if m else text


def _first_balanced(text: str) -> str | None:
    """Return the first balanced {...} or [...] block, ignoring braces in strings."""
    start = None
    opener = closer = ""
    for i, ch in enumerate(text):
        if start is None:
            if ch in "{[":
                start = i
                opener = ch
                closer = "}" if ch == "{" else "]"
            continue
        # scanning inside a candidate block
    if start is None:
        return None

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(text: str) -> Any:
    """Extract a JSON value (object or array) from arbitrary model text.

    Tries, in order: direct parse, fence-stripped parse, first balanced block,
    and a tolerant pass that removes trailing commas. Raises ``JsonExtractError``
    if all fail.
    """
    if not text or not text.strip():
        raise JsonExtractError("empty model output")

    candidates: list[str] = []
    stripped = _strip_fences(text).strip()
    candidates.append(stripped)
    block = _first_balanced(stripped)
    if block and block != stripped:
        candidates.append(block)

    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(_TRAILING_COMMA.sub(r"\1", cand))
        except json.JSONDecodeError:
            continue

    raise JsonExtractError("no valid JSON found in model output")
