import json
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from app.ppt.trace import TraceWriter, TracingCallbackHandler


def _result_event(name, result):
    return {
        "type": "task_result",
        "step": 1,
        "timestamp": "t",
        "payload": {"name": name, "result": result},
    }


async def test_merged_trace_file_matches_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path))
    w = TraceWriter("s1", "deck title")
    h = TracingCallbackHandler(w)

    # Two LLM calls from the dsl node (deck_spec + slide_planner).
    for i, label in enumerate(["deck_spec", "slide_planner"]):
        rid = f"run-{i}"
        await h.on_chat_model_start(
            {"name": "ChatOllama"},
            [[HumanMessage(content=f"prompt {i}")]],
            run_id=rid,
            metadata={"langgraph_node": "dsl", "trace_label": label},
        )
        gen = SimpleNamespace(text=f"raw {i}", message=None)
        await h.on_llm_end(SimpleNamespace(generations=[[gen]], llm_output={}), run_id=rid)

    # Node events incl. a render failure carrying a render_report.
    w.handle(("ppt",), _result_event("dsl", {"deck_spec": {"title": "t"}, "slide_dsls": [{}]}))
    w.handle(
        ("ppt",),
        _result_event(
            "render",
            {"render_report": {"attempted": True, "ok": False, "error": "boom", "stack": "S"}},
        ),
    )
    w.flush()

    data = json.loads((tmp_path / "s1" / "trace_latest.json").read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert isinstance(data["backend"], str) and data["backend"]
    assert isinstance(data["model"], str) and data["model"]
    assert [c["label"] for c in data["llm_calls"]] == ["deck_spec", "slide_planner"]
    assert data["llm_calls"][0]["prompt"].endswith("prompt 0")
    assert data["llm_calls"][1]["prompt"].endswith("prompt 1")
    assert data["llm_calls"][1]["raw_response"] == "raw 1"
    assert data["render"]["stack"] == "S"
    assert data["render"]["error"] == "boom"
    # render node event was promoted to error
    render_evs = [e for e in data["events"] if e["node"] == "render"]
    assert render_evs, "no render event found"
    assert render_evs[0]["status"] == "error"
