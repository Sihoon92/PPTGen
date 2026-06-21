"""Layout IR — the renderer-facing intermediate representation.

Produced deterministically by the compiler from a Slide DSL. Unlike the DSL, IR
elements carry absolute geometry (inches) and resolved style. Every element keeps
``source_node_id`` so QA/repair can map a rendered problem back to a DSL node.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# 16:9 widescreen canvas, inches.
CANVAS_W = 13.333
CANVAS_H = 7.5


class IRElement(BaseModel):
    source_node_id: str
    type: str  # text | bullets | metric | shape
    x: float
    y: float
    w: float
    h: float
    style: dict = Field(default_factory=dict)
    content: dict = Field(default_factory=dict)


class LayoutIR(BaseModel):
    slide_id: str
    canvas: dict = Field(default_factory=lambda: {"w": CANVAS_W, "h": CANVAS_H})
    elements: list[IRElement] = Field(default_factory=list)
