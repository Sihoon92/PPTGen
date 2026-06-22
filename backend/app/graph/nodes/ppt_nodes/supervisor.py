"""The supervisor: routing hub of the PPT subgraph.

Every stage returns here; the supervisor decides the next hop. Progression is a
forward pointer over ``[dsl, compiler, render]`` — once a turn's start stage is
chosen, ``pipeline_pos`` only advances, which guarantees termination (each stage
runs at most once per turn; ``step_count`` is a backstop).

The start stage is ``dsl`` for a fresh deck. When a deck already exists and a new
user message arrives (an edit), an LLM classifies which stage to restart from. A new
turn is detected by comparing the human-message count to ``handled_msg_count``.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.graph.state import PptState
from app.ppt.prompts import SUPERVISOR_INTENT_PROMPT
from app.ppt.trace import label_config

SupervisorNode = Callable[[PptState], Awaitable[dict]]

STAGES = ["dsl", "compiler", "render"]
MAX_STEPS = 8


def _human_count(state: PptState) -> int:
    return sum(
        1
        for m in state.get("messages", []) or []
        if getattr(m, "type", None) == "human" or m.__class__.__name__ == "HumanMessage"
    )


def _last_human(state: PptState) -> str:
    for m in reversed(state.get("messages", []) or []):
        if getattr(m, "type", None) == "human" or m.__class__.__name__ == "HumanMessage":
            return str(getattr(m, "content", ""))
    return ""


def _reset_from(idx: int) -> dict:
    """Clear outputs produced by stage ``idx`` and everything after it."""
    resets: dict = {"output_path": ""}
    if idx <= 1:
        resets["layout_irs"] = []
    if idx <= 0:
        resets["slide_dsls"] = []
    return resets


async def _classify_intent(model: BaseChatModel, request: str, config: RunnableConfig = None) -> str:
    """Edit request → start stage. Safe fallback to ``dsl`` (full regenerate)."""
    try:
        resp = await model.ainvoke(
            [HumanMessage(content=SUPERVISOR_INTENT_PROMPT.format(request=request))],
            label_config(config, "intent_classify"),
        )
        word = str(getattr(resp, "content", "")).strip().lower()
        for stage in STAGES:
            if stage in word:
                return stage
    except Exception:  # noqa: BLE001 - classification must never break the run
        pass
    return "dsl"


def route_from_supervisor(state: PptState) -> str:
    """Conditional-edge selector: the supervisor already wrote the decision to ``route``."""
    return state.get("route", "end")


def make_supervisor_node(model: BaseChatModel) -> SupervisorNode:
    async def supervisor(state: PptState, config: RunnableConfig = None) -> dict:
        step = state.get("step_count", 0) + 1
        if step > MAX_STEPS:
            return {"route": "end", "step_count": step}

        humans = _human_count(state)
        handled = state.get("handled_msg_count", 0)

        if humans > handled:
            # New user turn: pick the start stage, reset its downstream outputs.
            if state.get("output_path"):
                start = await _classify_intent(model, _last_human(state), config)
            else:
                start = "dsl"
            idx = STAGES.index(start)
            return {
                "route": start,
                "step_count": step,
                "pipeline_pos": idx,
                "handled_msg_count": humans,
                **_reset_from(idx),
            }

        # Same turn: advance the pointer toward the end.
        nxt = state.get("pipeline_pos", -1) + 1
        if nxt >= len(STAGES):
            return {"route": "end", "step_count": step}
        return {"route": STAGES[nxt], "step_count": step, "pipeline_pos": nxt}

    return supervisor
