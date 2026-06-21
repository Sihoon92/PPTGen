"""The three PPT work nodes: dsl → compiler → render.

Each folds what used to be several nodes:

- ``dsl``      : brief → DeckSpec → Slide DSL → validate  (LLM + deterministic check)
- ``compiler`` : Slide DSL → theme → Layout IR           (deterministic)
- ``render``   : Layout IR → .pptx + artifact/message     (Node sidecar)

All degrade gracefully: a parse/validation/render failure records an ``Issue`` (and,
for render, an apology message) instead of raising, so the SSE stream never crashes.
Domain logic is reused from ``app/ppt/*`` unchanged.
"""

from __future__ import annotations

import json
import os
from typing import Awaitable, Callable
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app.config import get_settings
from app.graph.state import PptState
from app.ppt.compiler import compile_slide
from app.ppt.dsl import DeckSpec, Issue, SlideDSL
from app.ppt.extract import JsonExtractError, extract_json
from app.ppt.prompts import DECK_SPEC_PROMPT, DSL_PLANNER_PROMPT, PRIMITIVE_CATALOG
from app.ppt.renderer import render_deck
from app.ppt.theme import resolve_theme
from app.ppt.validator import validate_deck

PptNode = Callable[[PptState], Awaitable[dict]]

_FAIL_MSG = (
    "죄송해요, 이번 요청으로는 슬라이드를 생성하지 못했어요. "
    "주제와 핵심 메시지를 조금 더 구체적으로 알려주시면 다시 시도할게요."
)


def _last_human(state: PptState) -> str:
    for m in reversed(state.get("messages", []) or []):
        if getattr(m, "type", None) == "human" or m.__class__.__name__ == "HumanMessage":
            return str(getattr(m, "content", ""))
    return ""


def make_dsl_node(model: BaseChatModel) -> PptNode:
    """brief → DeckSpec → Slide DSL → validate, all in one node.

    Absorbs the former deck_spec + dsl_planner + dsl_validator nodes. Two LLM calls:
    one for the deck plan, one for the slide layouts. Both fall back gracefully.
    """

    async def dsl(state: PptState) -> dict:
        brief = _last_human(state)

        # 1) Deck plan.
        resp = await model.ainvoke([HumanMessage(content=DECK_SPEC_PROMPT.format(brief=brief))])
        try:
            spec = DeckSpec.model_validate(extract_json(resp.content))
        except (JsonExtractError, ValueError):
            spec = DeckSpec(
                title=(brief[:60] or "Presentation"),
                audience="general",
                goal=(brief or "inform the audience"),
                tone="executive",
                narrative=[],
            )

        # 2) Slide layouts (all slides at once).
        prompt = DSL_PLANNER_PROMPT.format(
            catalog=PRIMITIVE_CATALOG,
            deck_spec=json.dumps(spec.model_dump(), ensure_ascii=False),
        )
        resp = await model.ainvoke([HumanMessage(content=prompt)])
        try:
            raw = extract_json(resp.content)
        except JsonExtractError:
            return {
                "deck_spec": spec.model_dump(),
                "slide_dsls": [],
                "issues": [Issue(stage="parse", code="json",
                                 message="planner output was not valid JSON").model_dump()],
            }

        # 3) Deterministic validation (keeps structurally-valid slides, reports the rest).
        slides, issues = validate_deck(raw)
        return {
            "deck_spec": spec.model_dump(),
            "slide_dsls": [s.model_dump() for s in slides],
            "issues": [i.model_dump() for i in issues],
        }

    return dsl


def compiler_node(state: PptState) -> dict:
    """Slide DSL → Layout IR. Resolves the theme internally; fully deterministic."""
    theme = resolve_theme(state.get("deck_spec"))
    irs: list[dict] = []
    for d in state.get("slide_dsls", []) or []:
        try:
            slide = SlideDSL.model_validate(d)
        except ValueError:
            continue
        irs.append(compile_slide(slide, theme).model_dump())
    return {"theme": theme, "layout_irs": irs}


async def render_node(state: PptState) -> dict:
    """Layout IR → .pptx via the Node sidecar, plus the artifact + user-facing message.

    Absorbs the former renderer + finalize nodes. On no-slides/failure, returns an
    apology message and no ``output_path`` so the supervisor ends the turn.
    """
    settings = get_settings()
    layout_irs = state.get("layout_irs", []) or []
    if not layout_irs:
        issues = list(state.get("issues", []) or [])
        issues.append(Issue(stage="render", code="no_slides",
                            message="no slides available to render").model_dump())
        return {"issues": issues, "messages": [AIMessage(content=_FAIL_MSG)]}

    session_id = state.get("session_id") or "session"
    artifact_id = uuid4().hex
    out_path = os.path.join(settings.artifacts_dir, session_id, f"deck_{artifact_id}.pptx")
    result = await render_deck(
        layout_irs, state.get("theme") or resolve_theme(), out_path, settings.node_bin
    )
    if not result.ok:
        issues = list(state.get("issues", []) or [])
        issues.append(Issue(stage="render", code="render_failed",
                            message=result.error or "render failed").model_dump())
        return {"issues": issues, "messages": [AIMessage(content=_FAIL_MSG)]}

    slide_count = len(layout_irs)
    title = (state.get("deck_spec") or {}).get("title", "발표 자료")
    artifact = {
        "id": artifact_id,
        "filename": "deck.pptx",
        "slide_count": slide_count,
        "download_url": f"/api/artifacts/{artifact_id}",
    }
    msg = f"'{title}' 슬라이드 {slide_count}장을 생성했어요. 아래에서 다운로드할 수 있습니다."
    return {
        "output_path": result.out_path,
        "artifact_id": artifact_id,
        "artifact": artifact,
        "messages": [AIMessage(content=msg)],
    }
