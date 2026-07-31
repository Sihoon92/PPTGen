from app.ppt.dsl import DeckSpec, Issue, LayoutNode, SlideDSL
from app.ppt.ir import CANVAS_H, CANVAS_W, IRElement, LayoutIR


def test_layout_node_nested_children():
    node = LayoutNode(
        id="cols",
        type="columns",
        props={"cols": 2},
        children=[
            LayoutNode(id="a", type="card", content={"heading": "A"}),
            LayoutNode(id="b", type="card", content={"heading": "B"}),
        ],
    )
    assert node.children[1].id == "b"
    # round-trips through dict (used for state serialization)
    assert LayoutNode.model_validate(node.model_dump()).type == "columns"


def test_slide_and_deck_spec():
    slide = SlideDSL(
        slide_id="s1",
        role="content",
        intent="explain",
        title="T",
        layout=LayoutNode(id="root", type="text", content={"text": "hi"}),
    )
    assert slide.layout.content == {"text": "hi"}
    spec = DeckSpec(title="x", audience="execs", goal="persuade", tone="executive")
    assert spec.narrative == []


def test_issue_defaults():
    issue = Issue(stage="dsl", code="unsupported_type", message="nope")
    assert issue.severity == "error"
    assert issue.slide_id is None


def test_layout_ir_default_canvas():
    ir = LayoutIR(
        slide_id="s1",
        elements=[IRElement(source_node_id="root", type="text", x=1, y=1, w=2, h=1)],
    )
    assert ir.canvas == {"w": CANVAS_W, "h": CANVAS_H}
    assert ir.elements[0].source_node_id == "root"
