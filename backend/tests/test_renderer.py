import json

from app.ppt.renderer import _parse_render_result, render_deck


def test_parse_preserves_stack_and_stderr():
    stdout = json.dumps(
        {"ok": False, "error": "boom", "stack": "Error: boom\n  at main"}
    ).encode("utf-8")
    r = _parse_render_result(stdout, b"warn on stderr", 1, "/x/out.pptx")
    assert r.ok is False
    assert r.error == "boom"
    assert r.stack == "Error: boom\n  at main"
    assert r.stderr == "warn on stderr"


def test_parse_does_not_truncate_error():
    big = "x" * 5000
    stdout = json.dumps({"ok": False, "error": big}).encode("utf-8")
    r = _parse_render_result(stdout, b"", 1, "/x/out.pptx")
    assert len(r.error) == 5000  # previously truncated to 500


def test_parse_success():
    stdout = json.dumps(
        {"ok": True, "out_path": "/x/out.pptx", "slide_count": 3}
    ).encode("utf-8")
    r = _parse_render_result(stdout, b"", 0, "/x/out.pptx")
    assert r.ok is True
    assert r.slide_count == 3
    assert r.stack is None
    assert r.stderr is None


def test_parse_non_json_stdout_falls_back_to_stderr():
    r = _parse_render_result(b"not json", b"real error text", 1, "/x/out.pptx")
    assert r.ok is False
    assert "real error text" in r.error
    assert r.stderr == "real error text"


async def test_render_deck_dumps_job_before_spawn(tmp_path):
    job_path = tmp_path / "render_job_test.json"
    out_path = tmp_path / "out.pptx"
    r = await render_deck(
        [{"slide_id": "s1", "elements": []}],
        {"colors": {"background": "FFFFFF"}},
        str(out_path),
        node_bin="definitely-not-a-real-binary-xyz",
        job_dump_path=str(job_path),
    )
    assert job_path.exists()  # written even though the binary is missing
    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["slides"][0]["slide_id"] == "s1"
    assert r.ok is False
