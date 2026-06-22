import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import HumanMessage

import app.graph.nodes.ppt_nodes.stages as stages
from app.graph.nodes.ppt import build_ppt_subgraph
from app.ppt.renderer import RenderResult
from app.ppt.trace import TracingCallbackHandler, TraceWriter

DECK_SPEC_JSON = (
    '{"title":"AI 전략","audience":"임원","goal":"설득","tone":"executive",'
    '"narrative":["문제","해결"]}'
)
DECK_DSL_JSON = (
    '[{"slide_id":"s1","role":"content","intent":"intro","title":"문제 정의",'
    '"layout":{"id":"root","type":"text","content":{"text":"핵심 메시지"}}},'
    '{"slide_id":"s2","role":"summary","intent":"wrap","title":"요약",'
    '"layout":{"id":"c","type":"callout","content":{"text":"실행을 시작하자"}}}]'
)


@pytest.fixture
def fake_render(monkeypatch):
    async def _render(layout_irs, theme, out_path, node_bin="node", job_dump_path=None):
        return RenderResult(ok=True, out_path=out_path, slide_count=len(layout_irs))

    monkeypatch.setattr(stages, "render_deck", _render)


@pytest.mark.asyncio
async def test_subgraph_generates_deck(fake_render):
    # supervisor → dsl (2 LLM calls) → compiler → render → END
    model = GenericFakeChatModel(messages=iter([DECK_SPEC_JSON, DECK_DSL_JSON]))
    graph = build_ppt_subgraph(model)
    out = await graph.ainvoke(
        {"messages": [HumanMessage("AI 도입 전략 발표 만들어줘")], "session_id": "s1"}
    )

    assert out["artifact_id"]
    assert out["output_path"].endswith(".pptx")
    assert out["artifact"]["slide_count"] == 2
    assert out["deck_spec"]["title"] == "AI 전략"
    assert "생성" in out["messages"][-1].content


@pytest.mark.asyncio
async def test_subgraph_handles_non_json_gracefully(fake_render):
    # model never emits JSON -> dsl yields no slides -> render apologizes, no output.
    # Forward pointer guarantees termination (no infinite re-routing to dsl).
    model = GenericFakeChatModel(messages=iter(["not json"] * 4))
    graph = build_ppt_subgraph(model)
    out = await graph.ainvoke(
        {"messages": [HumanMessage("회사 소개 자료를 대충 만들어줘 지금")], "session_id": "s2"}
    )
    assert not out.get("output_path")  # reset to "" then never rendered
    assert out.get("slide_dsls") == []
    assert "죄송" in out["messages"][-1].content


@pytest.mark.asyncio
async def test_subgraph_config_and_callbacks_reach_dsl_node(fake_render):
    """Regression: config (callbacks + configurable.trace_run_id) must propagate into
    the ppt subgraph's dsl node.  A missing ``config: RunnableConfig`` annotation on
    ``dsl`` would silently drop the callbacks, leaving writer.llm_calls empty.

    Assertion strategy: GenericFakeChatModel fires on_chat_model_start / on_llm_end
    through LangChain's base generate machinery (confirmed empirically), so we can
    assert that writer.llm_calls is non-empty and that the dsl node's two labelled
    calls ("deck_spec" and "slide_planner") are captured.  This assertion genuinely
    FAILS if config propagation breaks.
    """
    model = GenericFakeChatModel(messages=iter([DECK_SPEC_JSON, DECK_DSL_JSON]))
    graph = build_ppt_subgraph(model)

    writer = TraceWriter(session_id="wire-test", title="wiring regression")
    handler = TracingCallbackHandler(writer)

    await graph.ainvoke(
        {"messages": [HumanMessage("설정 전파 테스트")], "session_id": "wire-test"},
        config={
            "configurable": {"trace_run_id": "wire-test"},
            "callbacks": [handler],
        },
    )

    # callbacks must have been fired (non-empty means config reached dsl node)
    assert writer.llm_calls, "No LLM calls captured — config/callbacks did not reach dsl node"

    labels = {rec.get("label") for rec in writer.llm_calls}
    nodes = {rec.get("node") for rec in writer.llm_calls}

    assert "dsl" in nodes, f"Expected node='dsl' in llm_calls, got nodes={nodes}"
    assert "deck_spec" in labels, f"Expected label='deck_spec' in llm_calls, got labels={labels}"
    assert "slide_planner" in labels, f"Expected label='slide_planner' in llm_calls, got labels={labels}"
