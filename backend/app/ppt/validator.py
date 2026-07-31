"""Deterministic Slide DSL validation.

Turns raw (already JSON-parsed) planner output into validated ``SlideDSL`` objects
plus a list of structured ``Issue``s. Never raises on bad content — it reports.
The pipeline uses the issues to drive a bounded self-repair loop and, past the cap,
to drop invalid slides instead of crashing.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.ppt.dsl import CONTENT_TYPES, LAYOUT_TYPES, Issue, LayoutNode, SlideDSL

KNOWN_TYPES = LAYOUT_TYPES | CONTENT_TYPES
MAX_BULLETS = 7
MAX_BULLET_LEN = 120


def _unwrap(raw: Any) -> tuple[list[Any], list[Issue]]:
    """Accept either a bare list of slides or ``{"slides": [...]}``."""
    if isinstance(raw, dict) and "slides" in raw:
        raw = raw["slides"]
    if not isinstance(raw, list):
        return [], [Issue(stage="dsl", code="not_a_list", message="deck must be a list of slides")]
    return raw, []


def _validate_layout(node: LayoutNode, slide_id: str, seen: set[str], issues: list[Issue]) -> None:
    if node.id in seen:
        issues.append(
            Issue(stage="dsl", code="duplicate_node_id", message=f"node id '{node.id}' repeated",
                  slide_id=slide_id, node_id=node.id)
        )
    seen.add(node.id)

    t = node.type
    if t not in KNOWN_TYPES:
        issues.append(
            Issue(stage="dsl", code="unsupported_type",
                  message=f"type '{t}' is not supported in V1", slide_id=slide_id, node_id=node.id)
        )
        return

    n = len(node.children)
    if t == "split" and n != 2:
        issues.append(_arity(slide_id, node, "split needs exactly 2 children", n))
    elif t in ("columns", "grid"):
        cols = node.props.get("cols")
        if not isinstance(cols, int) or not 2 <= cols <= 4:
            issues.append(
                Issue(stage="dsl", code="bad_props",
                      message=f"{t} needs props.cols in 2..4", slide_id=slide_id, node_id=node.id)
            )
        elif t == "columns" and n != cols:
            issues.append(_arity(slide_id, node, f"columns needs {cols} children", n))
        elif t == "grid" and n == 0:
            issues.append(_arity(slide_id, node, "grid needs children", n))
    elif t == "stack" and n == 0:
        issues.append(_arity(slide_id, node, "stack needs children", n))
    elif t == "kpi_row":
        if n == 0:
            issues.append(_arity(slide_id, node, "kpi_row needs metric children", n))
        for ch in node.children:
            if ch.type != "metric":
                issues.append(
                    Issue(stage="dsl", code="bad_child",
                          message="kpi_row children must be metric", slide_id=slide_id, node_id=ch.id)
                )
    elif t == "callout":
        if not (node.content or {}).get("text"):
            issues.append(_missing_content(slide_id, node, "callout needs content.text"))
    elif t == "text":
        if not (node.content or {}).get("text"):
            issues.append(_missing_content(slide_id, node, "text needs content.text"))
    elif t == "bullets":
        _validate_bullets(node, slide_id, issues)
    elif t == "metric":
        if (node.content or {}).get("value") in (None, ""):
            issues.append(_missing_content(slide_id, node, "metric needs content.value"))

    for ch in node.children:
        _validate_layout(ch, slide_id, seen, issues)


def _validate_bullets(node: LayoutNode, slide_id: str, issues: list[Issue]) -> None:
    items = (node.content or {}).get("items")
    if not isinstance(items, list) or not items:
        issues.append(_missing_content(slide_id, node, "bullets needs non-empty content.items"))
        return
    if len(items) > MAX_BULLETS:
        issues.append(
            Issue(stage="dsl", severity="warning", code="too_many_bullets",
                  message=f"{len(items)} bullets exceeds {MAX_BULLETS}",
                  slide_id=slide_id, node_id=node.id)
        )
    for it in items:
        if isinstance(it, str) and len(it) > MAX_BULLET_LEN:
            issues.append(
                Issue(stage="dsl", severity="warning", code="long_bullet",
                      message="bullet text may overflow", slide_id=slide_id, node_id=node.id)
            )
            break


def _arity(slide_id: str, node: LayoutNode, msg: str, got: int) -> Issue:
    return Issue(stage="dsl", code="bad_arity", message=f"{msg} (got {got})",
                 slide_id=slide_id, node_id=node.id)


def _missing_content(slide_id: str, node: LayoutNode, msg: str) -> Issue:
    return Issue(stage="dsl", code="missing_content", message=msg,
                 slide_id=slide_id, node_id=node.id)


def validate_deck(raw: Any) -> tuple[list[SlideDSL], list[Issue]]:
    """Validate raw planner output. Returns (structurally valid slides, issues).

    A slide that fails pydantic parsing is excluded from the returned list and
    recorded as an issue. Slides that parse but violate V1 layout rules are kept
    (so partial rendering stays possible) while their issues are reported.
    """
    slides_raw, issues = _unwrap(raw)
    valid: list[SlideDSL] = []
    seen_slide_ids: set[str] = set()

    for i, item in enumerate(slides_raw):
        try:
            slide = SlideDSL.model_validate(item)
        except ValidationError as exc:
            sid = item.get("slide_id") if isinstance(item, dict) else None
            issues.append(
                Issue(stage="dsl", code="schema",
                      message=f"slide {sid or i} failed schema: {exc.error_count()} error(s)",
                      slide_id=sid)
            )
            continue

        if slide.slide_id in seen_slide_ids:
            issues.append(
                Issue(stage="dsl", code="duplicate_slide_id",
                      message=f"slide_id '{slide.slide_id}' repeated", slide_id=slide.slide_id)
            )
        seen_slide_ids.add(slide.slide_id)

        _validate_layout(slide.layout, slide.slide_id, set(), issues)
        valid.append(slide)

    if not slides_raw and not issues:
        issues.append(Issue(stage="dsl", code="empty_deck", message="deck has no slides"))
    return valid, issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
