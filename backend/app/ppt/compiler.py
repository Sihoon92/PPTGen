"""Deterministic Slide DSL -> Layout IR compiler.

This is the load-bearing module: it converts an abstract layout tree into absolute
geometry on a 13.333 x 7.5 in canvas. It is a placement engine, never a creator —
it adds no content the DSL did not specify. Every emitted element carries the id of
the DSL node it came from for repair traceability.

Layout strategy: a ``Rect`` is passed top-down; each container partitions its rect
among children (minus gaps) and recurses. Leaves emit terminal IR elements.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any

from app.ppt.dsl import SlideDSL
from app.ppt.ir import CANVAS_H, CANVAS_W, IRElement, LayoutIR

MARGIN = 0.5
TITLE_Y = 0.4
TITLE_H = 0.9
BODY_Y = 1.5
BODY_H = CANVAS_H - BODY_Y - MARGIN  # 5.5
GAP = 0.25
PAD = 0.2
USABLE_W = CANVAS_W - 2 * MARGIN  # 12.333


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    def inset(self, p: float) -> "Rect":
        return Rect(self.x + p, self.y + p, self.w - 2 * p, self.h - 2 * p)


def compile_slide(slide: SlideDSL, theme: dict[str, Any]) -> LayoutIR:
    elements: list[IRElement] = []
    size = theme["size"]
    colors = theme["colors"]
    fonts = theme["fonts"]

    # Title band
    if slide.title:
        elements.append(
            IRElement(
                source_node_id=slide.layout.id,
                type="text",
                x=MARGIN, y=TITLE_Y, w=USABLE_W, h=TITLE_H,
                style={"fontFace": fonts["title"], "fontSize": size["title"],
                       "bold": True, "color": colors["text"], "align": "left"},
                content={"text": slide.title},
            )
        )

    body = Rect(MARGIN, BODY_Y, USABLE_W, BODY_H)
    _emit(slide.layout.model_dump(), body, theme, elements, depth=0)
    return LayoutIR(slide_id=slide.slide_id, elements=elements)


def _split_lengths(total: float, weights: list[float], gap: float) -> list[float]:
    n = len(weights)
    avail = total - gap * (n - 1)
    s = sum(weights) or n
    return [avail * (w / s) for w in weights]


def _emit(node: dict, rect: Rect, theme: dict, out: list[IRElement], depth: int) -> None:
    t = node.get("type")
    children = node.get("children") or []
    props = node.get("props") or {}

    if t == "stack":
        _emit_stack(node, rect, theme, out, depth, props, children)
    elif t == "split":
        _emit_row(children, rect, theme, out, depth, props.get("ratio") or [1, 1])
    elif t == "columns":
        cols = props.get("cols", max(1, len(children)))
        _emit_row(children, rect, theme, out, depth, [1] * cols)
    elif t == "grid":
        _emit_grid(node, rect, theme, out, depth, props, children)
    elif t == "kpi_row":
        _emit_row(children, rect, theme, out, depth, [1] * max(1, len(children)))
    elif t == "card":
        _emit_card(node, rect, theme, out, depth)
    elif t == "callout":
        _emit_callout(node, rect, theme, out)
    elif t == "text":
        _emit_text(node, rect, theme, out, depth)
    elif t == "bullets":
        _emit_bullets(node, rect, theme, out)
    elif t == "metric":
        _emit_metric(node, rect, theme, out)
    # unknown types are silently skipped here; the validator already flagged them.


def _emit_stack(node, rect, theme, out, depth, props, children):
    if props.get("direction") == "horizontal":
        _emit_row(children, rect, theme, out, depth, [1] * max(1, len(children)))
        return
    if not children:
        return
    weights = props.get("weights") or [1] * len(children)
    heights = _split_lengths(rect.h, weights, GAP)
    y = rect.y
    for ch, h in zip(children, heights):
        _emit(ch, Rect(rect.x, y, rect.w, h), theme, out, depth + 1)
        y += h + GAP


def _emit_row(children, rect, theme, out, depth, weights):
    if not children:
        return
    weights = weights[: len(children)] + [1] * (len(children) - len(weights))
    widths = _split_lengths(rect.w, weights, GAP)
    x = rect.x
    for ch, w in zip(children, widths):
        _emit(ch, Rect(x, rect.y, w, rect.h), theme, out, depth + 1)
        x += w + GAP


def _emit_grid(node, rect, theme, out, depth, props, children):
    cols = props.get("cols", 2) or 2
    rows = props.get("rows") or ceil(len(children) / cols)
    cell_w = (rect.w - GAP * (cols - 1)) / cols
    cell_h = (rect.h - GAP * (rows - 1)) / rows if rows else rect.h
    for i, ch in enumerate(children):
        r, c = divmod(i, cols)
        cx = rect.x + c * (cell_w + GAP)
        cy = rect.y + r * (cell_h + GAP)
        _emit(ch, Rect(cx, cy, cell_w, cell_h), theme, out, depth + 1)


def _emit_card(node, rect, theme, out, depth):
    colors = theme["colors"]
    out.append(
        IRElement(
            source_node_id=node["id"], type="shape",
            x=rect.x, y=rect.y, w=rect.w, h=rect.h,
            style={"shape": "roundRect", "fill": colors["surface"], "line": colors["card_line"]},
        )
    )
    inner = rect.inset(PAD)
    children = node.get("children") or []
    content = node.get("content") or {}
    if children:
        weights = [1] * len(children)
        heights = _split_lengths(inner.h, weights, GAP)
        y = inner.y
        for ch, h in zip(children, heights):
            _emit(ch, Rect(inner.x, y, inner.w, h), theme, out, depth + 1)
            y += h + GAP
        return
    # content-form card: optional heading + body
    y = inner.y
    heading = content.get("heading")
    if heading:
        hh = 0.4
        out.append(
            IRElement(
                source_node_id=node["id"], type="text",
                x=inner.x, y=y, w=inner.w, h=hh,
                style={"fontFace": theme["fonts"]["body"], "fontSize": theme["size"]["heading"],
                       "bold": True, "color": colors["text"], "align": "left"},
                content={"text": heading},
            )
        )
        y += hh + GAP / 2
    body = content.get("body")
    body_rect = Rect(inner.x, y, inner.w, max(0.3, inner.y + inner.h - y))
    if isinstance(body, dict):
        # A body is an inline content primitive: its payload (items/text) lives at the
        # top level, so wrap it under "content" for the leaf emitters.
        _emit({"id": node["id"], "type": body.get("type"), "content": body},
              body_rect, theme, out, depth + 1)
    elif isinstance(content.get("text"), str):
        _emit({"id": node["id"], "type": "text", "content": {"text": content["text"]}},
              body_rect, theme, out, depth + 1)


def _emit_callout(node, rect, theme, out):
    colors = theme["colors"]
    out.append(
        IRElement(
            source_node_id=node["id"], type="shape",
            x=rect.x, y=rect.y, w=rect.w, h=rect.h,
            style={"shape": "roundRect", "fill": colors["callout_fill"], "line": colors["primary"]},
        )
    )
    text = (node.get("content") or {}).get("text", "")
    inner = rect.inset(PAD)
    out.append(
        IRElement(
            source_node_id=node["id"], type="text",
            x=inner.x, y=inner.y, w=inner.w, h=inner.h,
            style={"fontFace": theme["fonts"]["body"], "fontSize": theme["size"]["body"],
                   "bold": True, "color": colors["primary"], "align": "left", "valign": "middle"},
            content={"text": text},
        )
    )


def _emit_text(node, rect, theme, out, depth):
    colors = theme["colors"]
    out.append(
        IRElement(
            source_node_id=node["id"], type="text",
            x=rect.x, y=rect.y, w=rect.w, h=rect.h,
            style={"fontFace": theme["fonts"]["body"], "fontSize": theme["size"]["body"],
                   "color": colors["text"], "align": "left"},
            content={"text": (node.get("content") or {}).get("text", "")},
        )
    )


def _emit_bullets(node, rect, theme, out):
    items = (node.get("content") or {}).get("items") or []
    out.append(
        IRElement(
            source_node_id=node["id"], type="bullets",
            x=rect.x, y=rect.y, w=rect.w, h=rect.h,
            style={"fontFace": theme["fonts"]["body"], "fontSize": theme["size"]["body"],
                   "color": theme["colors"]["text"], "align": "left"},
            content={"items": items},
        )
    )


def _emit_metric(node, rect, theme, out):
    colors = theme["colors"]
    size = theme["size"]
    content = node.get("content") or {}
    value_h = min(rect.h * 0.55, 1.1)
    out.append(
        IRElement(
            source_node_id=node["id"], type="text",
            x=rect.x, y=rect.y, w=rect.w, h=value_h,
            style={"fontFace": theme["fonts"]["title"], "fontSize": size["metric_value"],
                   "bold": True, "color": colors["primary"], "align": "center", "valign": "bottom"},
            content={"text": str(content.get("value", ""))},
        )
    )
    label_parts = [p for p in (content.get("label"), content.get("caption")) if p]
    out.append(
        IRElement(
            source_node_id=node["id"], type="text",
            x=rect.x, y=rect.y + value_h, w=rect.w, h=max(0.3, rect.h - value_h),
            style={"fontFace": theme["fonts"]["body"], "fontSize": size["metric_label"],
                   "color": colors["muted"], "align": "center", "valign": "top"},
            content={"text": "\n".join(label_parts)},
        )
    )
