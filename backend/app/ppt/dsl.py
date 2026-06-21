"""Slide DSL v1 models.

The LLM produces these (deck intent + slide structure) and nothing below them:
no coordinates, no font sizes, no renderer options. A deterministic compiler turns
the DSL into a Layout IR (see ``ir.py``).

``LayoutNode.type`` is intentionally a plain ``str`` (not a ``Literal``) so the model
may emit a deferred primitive (e.g. ``timeline``) without a hard pydantic failure;
the deterministic validator (see ``validator.py``) enforces the V1 allowlist and
reports an ``unsupported_type`` issue instead. This keeps the type system from
precluding future primitives.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# V1 layout containers. Kept small on purpose; combinations are allowed.
LayoutType = Literal["stack", "split", "columns", "grid", "card", "kpi_row", "callout"]
# V1 leaf content primitives.
ContentType = Literal["text", "bullets", "metric", "callout"]

# Allowlists the validator enforces (str sets for cheap membership checks).
LAYOUT_TYPES: frozenset[str] = frozenset(
    {"stack", "split", "columns", "grid", "card", "kpi_row", "callout"}
)
CONTENT_TYPES: frozenset[str] = frozenset({"text", "bullets", "metric", "callout"})


class LayoutNode(BaseModel):
    """A node in a slide's layout tree (container or leaf).

    ``content`` carries leaf payloads, e.g. ``{"text": "..."}`` for ``text``,
    ``{"items": [...]}`` for ``bullets``, ``{"label","value","caption"}`` for ``metric``.
    """

    id: str
    type: str
    props: dict = Field(default_factory=dict)
    content: dict | None = None
    children: list["LayoutNode"] = Field(default_factory=list)


class SlideDSL(BaseModel):
    slide_id: str
    role: str
    intent: str
    title: str
    layout: LayoutNode
    visual_guidance: dict = Field(default_factory=dict)
    constraints: dict = Field(default_factory=dict)


class DeckSpec(BaseModel):
    """Deck-level planning info. No layout, no coordinates."""

    title: str
    audience: str
    goal: str
    tone: str
    narrative: list[str] = Field(default_factory=list)


Severity = Literal["error", "warning"]


class Issue(BaseModel):
    """Structured validation/QA finding, routable back to a slide/node for repair."""

    stage: str  # parse | dsl | render | qa
    severity: Severity = "error"
    code: str
    message: str
    slide_id: str | None = None
    node_id: str | None = None


LayoutNode.model_rebuild()
