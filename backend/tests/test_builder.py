import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.builder import build_graph
from app.graph.nodes.ppt import PPT_STUB_MESSAGE


def _fake_model(text="hi from fake"):
    return GenericFakeChatModel(messages=iter([text]))


@pytest.mark.asyncio
async def test_graph_chat_mode_calls_llm():
    graph = build_graph(_fake_model("fake reply"), InMemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}
    out = await graph.ainvoke(
        {"messages": [HumanMessage("hi")], "mode": "chat", "session_id": "t1"}, cfg
    )
    assert out["messages"][-1].content == "fake reply"


@pytest.mark.asyncio
async def test_graph_ppt_mode_returns_stub():
    graph = build_graph(_fake_model(), InMemorySaver())
    cfg = {"configurable": {"thread_id": "t2"}}
    out = await graph.ainvoke(
        {"messages": [HumanMessage("slides")], "mode": "ppt", "session_id": "t2"}, cfg
    )
    assert out["messages"][-1].content == PPT_STUB_MESSAGE


@pytest.mark.asyncio
async def test_graph_persists_history_across_calls():
    graph = build_graph(
        GenericFakeChatModel(messages=iter(["first reply", "second reply"])),
        InMemorySaver(),
    )
    cfg = {"configurable": {"thread_id": "t3"}}
    await graph.ainvoke(
        {"messages": [HumanMessage("first")], "mode": "chat", "session_id": "t3"}, cfg
    )
    out2 = await graph.ainvoke(
        {"messages": [HumanMessage("second")], "mode": "chat", "session_id": "t3"}, cfg
    )
    assert len(out2["messages"]) >= 4  # turn1 (human+ai) + turn2 (human+ai)
