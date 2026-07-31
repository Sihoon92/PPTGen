"""Unit tests for the supervisor routing hub."""

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app.graph.nodes.ppt_nodes.supervisor import (
    make_supervisor_node,
    route_from_supervisor,
)


def _model(*replies):
    return GenericFakeChatModel(messages=iter(list(replies) or ["dsl"]))


def test_route_selector_reads_route_key():
    assert route_from_supervisor({"route": "compiler"}) == "compiler"
    assert route_from_supervisor({}) == "end"


@pytest.mark.asyncio
async def test_fresh_turn_starts_at_dsl_and_resets_downstream():
    sup = make_supervisor_node(_model())
    out = await sup({"messages": [HumanMessage("발표 만들어줘")]})
    assert out["route"] == "dsl"
    assert out["pipeline_pos"] == 0
    assert out["handled_msg_count"] == 1
    # downstream outputs cleared so regeneration is clean
    assert out["slide_dsls"] == [] and out["layout_irs"] == [] and out["output_path"] == ""


@pytest.mark.asyncio
async def test_same_turn_advances_pointer():
    sup = make_supervisor_node(_model())
    base = {"messages": [HumanMessage("x")], "handled_msg_count": 1}
    # pos 0 (dsl done) -> compiler
    assert (await sup({**base, "pipeline_pos": 0}))["route"] == "compiler"
    # pos 1 (compiler done) -> render
    assert (await sup({**base, "pipeline_pos": 1}))["route"] == "render"
    # pos 2 (render done) -> end
    assert (await sup({**base, "pipeline_pos": 2}))["route"] == "end"


@pytest.mark.asyncio
async def test_loop_guard_ends_after_max_steps():
    sup = make_supervisor_node(_model())
    out = await sup({"messages": [HumanMessage("x")], "step_count": 8})
    assert out["route"] == "end"


@pytest.mark.asyncio
async def test_edit_turn_classifies_start_stage_via_llm():
    # deck already exists (output_path set) + a new, unhandled human message
    sup = make_supervisor_node(_model("compiler"))
    state = {
        "messages": [HumanMessage("처음"), AIMessage("done"), HumanMessage("레이아웃만 바꿔줘")],
        "handled_msg_count": 1,
        "output_path": "/tmp/deck.pptx",
        "slide_dsls": [{"slide_id": "s1"}],
        "layout_irs": [{"slide_id": "s1"}],
    }
    out = await sup(state)
    assert out["route"] == "compiler"
    assert out["pipeline_pos"] == 1
    assert out["handled_msg_count"] == 2
    # compiler restart clears IR + output but keeps slide_dsls
    assert out["layout_irs"] == [] and out["output_path"] == ""
    assert "slide_dsls" not in out


@pytest.mark.asyncio
async def test_edit_classification_falls_back_to_dsl():
    # model returns gibberish -> safe fallback to full regenerate (dsl)
    sup = make_supervisor_node(_model("???"))
    state = {
        "messages": [HumanMessage("a"), AIMessage("done"), HumanMessage("바꿔")],
        "handled_msg_count": 1,
        "output_path": "/tmp/deck.pptx",
    }
    out = await sup(state)
    assert out["route"] == "dsl"
    assert out["pipeline_pos"] == 0
