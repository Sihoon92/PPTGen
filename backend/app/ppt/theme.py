"""Theme resolution.

The DSL only expresses style *intent* (``visual_guidance``); concrete colors, fonts
and sizes are decided here so the LLM never hand-picks hex values. V1 ships one
theme (``consulting_clean``). Colors are stored as bare hex (no ``#``) to match the
PptxGenJS convention used by the renderer.
"""

from __future__ import annotations

from typing import Any

CONSULTING_CLEAN: dict[str, Any] = {
    "name": "consulting_clean",
    "colors": {
        "background": "FFFFFF",
        "text": "1F2937",
        "muted": "6B7280",
        "primary": "2563EB",
        "accent": "F59E0B",
        "surface": "F8FAFC",
        "card_line": "E5E7EB",
        "callout_fill": "EEF6FF",
    },
    "fonts": {"title": "Aptos Display", "body": "Aptos"},
    "size": {
        "title": 32,
        "heading": 18,
        "body": 14,
        "caption": 10,
        "metric_value": 30,
        "metric_label": 12,
    },
}


def resolve_theme(deck_spec: dict | None = None) -> dict[str, Any]:
    """Return a concrete theme. V1 always returns ``consulting_clean`` (deep-copied)."""
    import copy

    return copy.deepcopy(CONSULTING_CLEAN)
