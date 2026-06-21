import pytest

from app.ppt.extract import JsonExtractError, extract_json


def test_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_fenced_json():
    text = "Sure!\n```json\n{\"slides\": [1, 2]}\n```\nDone."
    assert extract_json(text) == {"slides": [1, 2]}


def test_prose_wrapped_block():
    text = 'Here you go: [{"slide_id": "s1"}] hope it helps'
    assert extract_json(text) == [{"slide_id": "s1"}]


def test_trailing_comma_tolerated():
    assert extract_json('{"a": 1, "b": [2, 3,],}') == {"a": 1, "b": [2, 3]}


def test_braces_inside_strings_ignored():
    assert extract_json('{"text": "a } b ] c"}') == {"text": "a } b ] c"}


def test_empty_raises():
    with pytest.raises(JsonExtractError):
        extract_json("   ")


def test_garbage_raises():
    with pytest.raises(JsonExtractError):
        extract_json("no json here at all")
