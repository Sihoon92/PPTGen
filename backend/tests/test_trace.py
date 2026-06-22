import json

from app.ppt.trace import TraceWriter, label_config


def _result_event(name, result):
    return {
        "type": "task_result",
        "step": 1,
        "timestamp": "t",
        "payload": {"name": name, "result": result},
    }


def test_label_config_merges_metadata_without_mutating():
    cfg = {"configurable": {"thread_id": "s1"}, "metadata": {"a": 1}}
    out = label_config(cfg, "deck_spec")
    assert out["metadata"]["trace_label"] == "deck_spec"
    assert out["metadata"]["a"] == 1
    assert out["configurable"]["thread_id"] == "s1"
    assert "trace_label" not in (cfg["metadata"])  # original untouched


def test_label_config_handles_none():
    out = label_config(None, "intent_classify")
    assert out["metadata"]["trace_label"] == "intent_classify"


def test_render_failure_marks_status_error_and_captures_report():
    w = TraceWriter("s1", "title")
    report = {"attempted": True, "ok": False, "error": "boom", "stack": "S"}
    ev = w.handle(
        ("ppt",),
        _result_event("render", {"issues": [{"code": "render_failed"}], "render_report": report}),
    )
    assert ev["status"] == "error"
    assert w.render == report


def test_render_success_keeps_done_status():
    w = TraceWriter("s1", "title")
    ev = w.handle(
        ("ppt",),
        _result_event("render", {"artifact": {"slide_count": 2}, "output_path": "/x.pptx"}),
    )
    assert ev["status"] == "done"
    assert w.render is None


def test_ok_true_when_no_errors_and_no_render():
    w = TraceWriter("s1", "title")
    w.handle(("ppt",), _result_event("dsl", {"deck_spec": {"title": "t"}, "slide_dsls": [{}]}))
    assert w._ok() is True


async def test_flush_writes_extended_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path))
    w = TraceWriter("s1", "deck title")
    w.add_llm_call({"seq": 1, "label": "deck_spec", "prompt": "p", "raw_response": "r"})
    w.handle(("ppt",), _result_event("render", {"render_report": {"attempted": True, "ok": False}}))
    w.flush()

    data = json.loads((tmp_path / "s1" / "trace_latest.json").read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert data["backend"]  # non-empty (default "ollama")
    assert data["model"]
    assert len(data["llm_calls"]) == 1
    assert data["render"] == {"attempted": True, "ok": False}
    assert "events" in data  # node array key preserved for the frontend
    assert (tmp_path / "traces" / "latest.json").exists()
