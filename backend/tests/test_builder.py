import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.builder import build_graph


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
async def test_graph_ppt_mode_generates_deck(monkeypatch):
    import app.graph.nodes.ppt_nodes.stages as stages
    from app.ppt.renderer import RenderResult

    async def _render(layout_irs, theme, out_path, node_bin="node"):
        return RenderResult(ok=True, out_path=out_path, slide_count=len(layout_irs))

    monkeypatch.setattr(stages, "render_deck", _render)

    deck_spec = '{"title":"T","audience":"a","goal":"g","tone":"executive","narrative":["x"]}'
    deck_dsl = (
        '[{"slide_id":"s1","role":"content","intent":"i","title":"Slide",'
        '"layout":{"id":"root","type":"text","content":{"text":"hi"}}}]'
    )
    model = GenericFakeChatModel(messages=iter([deck_spec, deck_dsl]))
    graph = build_graph(model, InMemorySaver())
    cfg = {"configurable": {"thread_id": "t2"}}
    out = await graph.ainvoke(
        {"messages": [HumanMessage("make slides about our Q3 results please")],
         "mode": "ppt", "session_id": "t2"}, cfg
    )
    assert "생성" in out["messages"][-1].content


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
