from app.ppt.validator import has_errors, validate_deck


def _slide(layout, slide_id="s1"):
    return {
        "slide_id": slide_id,
        "role": "content",
        "intent": "x",
        "title": "T",
        "layout": layout,
    }


def _codes(issues):
    return {i.code for i in issues}


def test_valid_columns_deck():
    layout = {
        "id": "cols",
        "type": "columns",
        "props": {"cols": 2},
        "children": [
            {"id": "a", "type": "text", "content": {"text": "A"}},
            {"id": "b", "type": "text", "content": {"text": "B"}},
        ],
    }
    slides, issues = validate_deck([_slide(layout)])
    assert len(slides) == 1
    assert not has_errors(issues)


def test_split_wrong_arity():
    layout = {
        "id": "sp",
        "type": "split",
        "children": [{"id": "a", "type": "text", "content": {"text": "A"}}],
    }
    _, issues = validate_deck([_slide(layout)])
    assert "bad_arity" in _codes(issues)


def test_unsupported_type():
    layout = {"id": "t", "type": "timeline", "children": []}
    _, issues = validate_deck([_slide(layout)])
    assert "unsupported_type" in _codes(issues)


def test_columns_cols_mismatch():
    layout = {
        "id": "cols",
        "type": "columns",
        "props": {"cols": 3},
        "children": [{"id": "a", "type": "text", "content": {"text": "A"}}],
    }
    _, issues = validate_deck([_slide(layout)])
    assert "bad_arity" in _codes(issues)


def test_kpi_row_requires_metric_children():
    layout = {
        "id": "kpi",
        "type": "kpi_row",
        "children": [{"id": "a", "type": "text", "content": {"text": "A"}}],
    }
    _, issues = validate_deck([_slide(layout)])
    assert "bad_child" in _codes(issues)


def test_duplicate_node_id():
    layout = {
        "id": "dup",
        "type": "stack",
        "children": [
            {"id": "dup", "type": "text", "content": {"text": "A"}},
        ],
    }
    _, issues = validate_deck([_slide(layout)])
    assert "duplicate_node_id" in _codes(issues)


def test_duplicate_slide_id():
    layout = {"id": "t", "type": "text", "content": {"text": "A"}}
    _, issues = validate_deck([_slide(layout, "s1"), _slide(layout, "s1")])
    assert "duplicate_slide_id" in _codes(issues)


def test_missing_text_content():
    layout = {"id": "t", "type": "text", "content": {}}
    _, issues = validate_deck([_slide(layout)])
    assert "missing_content" in _codes(issues)


def test_bullets_too_many_is_warning():
    layout = {
        "id": "b",
        "type": "bullets",
        "content": {"items": [f"item {i}" for i in range(9)]},
    }
    slides, issues = validate_deck([_slide(layout)])
    assert len(slides) == 1
    assert "too_many_bullets" in _codes(issues)
    assert not has_errors(issues)  # warning only


def test_schema_failure_excludes_slide():
    # missing required 'title'
    bad = {"slide_id": "s1", "role": "content", "intent": "x",
           "layout": {"id": "t", "type": "text", "content": {"text": "A"}}}
    slides, issues = validate_deck([bad])
    assert slides == []
    assert "schema" in _codes(issues)


def test_unwrap_slides_key():
    layout = {"id": "t", "type": "text", "content": {"text": "A"}}
    slides, issues = validate_deck({"slides": [_slide(layout)]})
    assert len(slides) == 1


def test_empty_deck():
    _, issues = validate_deck([])
    assert "empty_deck" in _codes(issues)
