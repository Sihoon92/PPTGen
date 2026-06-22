from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from app.ppt.trace import TraceWriter, TracingCallbackHandler


async def test_handler_records_prompt_and_raw():
    w = TraceWriter("s1", "title")
    h = TracingCallbackHandler(w)
    await h.on_chat_model_start(
        {"name": "ChatOllama"},
        [[HumanMessage(content="hello prompt")]],
        run_id="run-1",
        metadata={"langgraph_node": "dsl", "trace_label": "deck_spec"},
    )
    gen = SimpleNamespace(text="raw output", message=None)
    response = SimpleNamespace(generations=[[gen]], llm_output={"token_usage": {"output": 5}})
    await h.on_llm_end(response, run_id="run-1")

    assert len(w.llm_calls) == 1
    rec = w.llm_calls[0]
    assert rec["seq"] == 1
    assert rec["node"] == "dsl"
    assert rec["label"] == "deck_spec"
    assert "hello prompt" in rec["prompt"]
    assert rec["raw_response"] == "raw output"
    assert rec["status"] == "ok"
    assert rec["token_usage"] == {"output": 5}


async def test_handler_records_error():
    w = TraceWriter("s1", "title")
    h = TracingCallbackHandler(w)
    await h.on_chat_model_start(
        {"name": "ChatOllama"},
        [[HumanMessage(content="p")]],
        run_id="run-2",
        metadata={"langgraph_node": "dsl", "trace_label": "slide_planner"},
    )
    await h.on_llm_error(RuntimeError("model exploded"), run_id="run-2")

    assert len(w.llm_calls) == 1
    rec = w.llm_calls[0]
    assert rec["status"] == "error"
    assert "model exploded" in rec["error"]


async def test_handler_ignores_unmatched_end():
    w = TraceWriter("s1", "title")
    h = TracingCallbackHandler(w)
    # on_llm_end with no prior start must not raise and must not append.
    await h.on_llm_end(SimpleNamespace(generations=[[]], llm_output={}), run_id="ghost")
    assert w.llm_calls == []
