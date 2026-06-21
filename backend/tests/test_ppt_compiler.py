from app.ppt.compiler import (
    BODY_H,
    BODY_Y,
    CANVAS_H,
    CANVAS_W,
    GAP,
    MARGIN,
    USABLE_W,
    compile_slide,
)
from app.ppt.dsl import LayoutNode, SlideDSL
from app.ppt.theme import resolve_theme

THEME = resolve_theme()


def _slide(layout: LayoutNode) -> SlideDSL:
    return SlideDSL(slide_id="s1", role="content", intent="x", title="Title", layout=layout)


def _within_canvas(el) -> bool:
    return (
        el.x >= -1e-6
        and el.y >= -1e-6
        and el.x + el.w <= CANVAS_W + 1e-6
        and el.y + el.h <= CANVAS_H + 1e-6
    )


def test_title_element_emitted_in_band():
    ir = compile_slide(_slide(LayoutNode(id="t", type="text", content={"text": "hi"})), THEME)
    title = ir.elements[0]
    assert title.content["text"] == "Title"
    assert title.style["fontSize"] == THEME["size"]["title"]
    assert all(_within_canvas(e) for e in ir.elements)


def test_columns_equal_width_and_gap():
    layout = LayoutNode(
        id="cols", type="columns", props={"cols": 3},
        children=[
            LayoutNode(id="a", type="text", content={"text": "A"}),
            LayoutNode(id="b", type="text", content={"text": "B"}),
            LayoutNode(id="c", type="text", content={"text": "C"}),
        ],
    )
    ir = compile_slide(_slide(layout), THEME)
    cols = [e for e in ir.elements if e.source_node_id in {"a", "b", "c"}]
    assert len(cols) == 3
    expected_w = (USABLE_W - 2 * GAP) / 3
    for e in cols:
        assert abs(e.w - expected_w) < 1e-6
    xs = sorted(e.x for e in cols)
    assert abs((xs[1] - xs[0]) - (expected_w + GAP)) < 1e-6
    assert all(_within_canvas(e) for e in ir.elements)


def test_split_ratio():
    layout = LayoutNode(
        id="sp", type="split", props={"ratio": [3, 1]},
        children=[
            LayoutNode(id="l", type="text", content={"text": "L"}),
            LayoutNode(id="r", type="text", content={"text": "R"}),
        ],
    )
    ir = compile_slide(_slide(layout), THEME)
    left = next(e for e in ir.elements if e.source_node_id == "l")
    right = next(e for e in ir.elements if e.source_node_id == "r")
    assert left.w > right.w
    assert abs(left.w / right.w - 3.0) < 0.05


def test_card_emits_background_shape_and_inner_content():
    layout = LayoutNode(
        id="card1", type="card",
        content={"heading": "H", "body": {"type": "bullets", "items": ["x", "y"]}},
    )
    ir = compile_slide(_slide(layout), THEME)
    shapes = [e for e in ir.elements if e.type == "shape"]
    assert len(shapes) == 1 and shapes[0].style["shape"] == "roundRect"
    bullets = next(e for e in ir.elements if e.type == "bullets")
    assert bullets.content["items"] == ["x", "y"]
    # inner content is inset within the card
    assert bullets.x > shapes[0].x


def test_kpi_row_metric_two_elements_each():
    layout = LayoutNode(
        id="kpi", type="kpi_row",
        children=[
            LayoutNode(id="m1", type="metric", content={"label": "Rev", "value": "-42%"}),
            LayoutNode(id="m2", type="metric", content={"label": "NPS", "value": "+9"}),
        ],
    )
    ir = compile_slide(_slide(layout), THEME)
    m1 = [e for e in ir.elements if e.source_node_id == "m1"]
    assert len(m1) == 2  # value + label
    assert any(e.content["text"] == "-42%" for e in m1)
    assert all(_within_canvas(e) for e in ir.elements)


def test_source_node_ids_preserved():
    layout = LayoutNode(
        id="stack", type="stack",
        children=[
            LayoutNode(id="a", type="text", content={"text": "A"}),
            LayoutNode(id="b", type="callout", content={"text": "B"}),
        ],
    )
    ir = compile_slide(_slide(layout), THEME)
    ids = {e.source_node_id for e in ir.elements}
    assert {"a", "b"}.issubset(ids)


def test_body_region_constants():
    assert abs(BODY_H - (CANVAS_H - BODY_Y - MARGIN)) < 1e-9
