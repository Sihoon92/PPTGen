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
import logging
import os
from typing import Awaitable, Callable
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.config import get_settings
from app.graph.state import PptState
from app.ppt.compiler import compile_slide
from app.ppt.dsl import DeckSpec, Issue, SlideDSL
from app.ppt.extract import JsonExtractError, extract_json
from app.ppt.prompts import DECK_SPEC_PROMPT, DSL_PLANNER_PROMPT, PRIMITIVE_CATALOG
from app.ppt.renderer import render_deck
from app.ppt.trace import label_config
from app.ppt.theme import resolve_theme
from app.ppt.validator import validate_deck

PptNode = Callable[[PptState, RunnableConfig | None], Awaitable[dict]]

logger = logging.getLogger("app.ppt")

# 파싱 실패 시 원본 모델 출력에서 보존할 스니펫 길이.
# 사내 internal API 가 200 + 빈/깨진 본문을 줄 때 그 실체를 로그·trace 에서 즉시 식별하기 위함.
_SNIPPET = 300

_FAIL_MSG = (
    "죄송해요, 이번 요청으로는 슬라이드를 생성하지 못했어요. "
    "주제와 핵심 메시지를 조금 더 구체적으로 알려주시면 다시 시도할게요."
)


def _issue_codes(issues: list[dict]) -> set[str]:
    return {str(i.get("code")) for i in issues if isinstance(i, dict)}


def _fail_message(issues: list[dict]) -> str:
    """실패 사유(issue 코드)에 따라 사용자에게 보일 구체 메시지를 고른다.

    모든 메시지는 기존 톤을 유지하고 회귀(``"죄송" in message`` 단언)를 지키기 위해
    "죄송해요,"로 시작한다. 사유를 특정할 수 없을 때만 일반 메시지로 떨어진다.
    """
    codes = _issue_codes(issues)
    if "render_failed" in codes:
        return "죄송해요, PPTX 렌더링 중 오류가 발생했어요. (자세한 내용은 실행 트레이스를 확인해 주세요.)"
    if codes & {"json", "deck_spec_json"}:
        return (
            "죄송해요, 슬라이드 설계 데이터(JSON) 생성에 실패했어요. "
            "AI 모델이 올바른 JSON 형식으로 응답하지 않았어요."
        )
    if codes & {"empty_deck", "not_a_list", "schema"}:
        return "죄송해요, 생성된 슬라이드가 구조 검증을 통과하지 못했어요."
    return _FAIL_MSG


def _fail_reason(issues: list[dict]) -> str | None:
    """``render_report.reason`` 용 요약: 가장 상류의 핵심 실패 issue를 ``stage/code: message``로.

    ``no_slides``(렌더 단계의 증상)보다 상류 원인(파싱/검증 실패)을 우선해 표면화한다.
    """
    priority = ("render_failed", "json", "deck_spec_json", "empty_deck",
                "not_a_list", "schema", "no_slides")
    by_code = {str(i.get("code")): i for i in issues if isinstance(i, dict)}
    for code in priority:
        if code in by_code:
            it = by_code[code]
            return f"{it.get('stage')}/{code}: {it.get('message')}"
    for i in issues:  # 우선순위 밖이면 첫 issue
        if isinstance(i, dict):
            return f"{i.get('stage')}/{i.get('code')}: {i.get('message')}"
    return None


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

    async def dsl(state: PptState, config: RunnableConfig = None) -> dict:
        brief = _last_human(state)
        pre_issues: list[dict] = []

        # 1) Deck plan.
        resp = await model.ainvoke(
            [HumanMessage(content=DECK_SPEC_PROMPT.format(brief=brief))],
            label_config(config, "deck_spec"),
        )
        try:
            spec = DeckSpec.model_validate(extract_json(resp.content))
        except (JsonExtractError, ValueError) as exc:
            # 이전엔 조용히 fallback 했던 지점: 동작(graceful fallback)은 유지하되 사유를
            # 로그와 issue 로 표면화해 연쇄 실패의 숨은 시발점이 보이게 한다.
            snippet = str(resp.content)[:_SNIPPET]
            logger.warning(
                "deck_spec JSON 파싱 실패(%s) → fallback DeckSpec 사용. raw=%r",
                type(exc).__name__, snippet,
            )
            pre_issues.append(Issue(
                stage="parse", severity="warning", code="deck_spec_json",
                message=f"deck plan JSON 파싱 실패 → fallback 사용. raw~ {snippet}",
            ).model_dump())
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
        resp = await model.ainvoke(
            [HumanMessage(content=prompt)], label_config(config, "slide_planner")
        )
        try:
            raw = extract_json(resp.content)
        except JsonExtractError:
            snippet = str(resp.content)[:_SNIPPET]
            logger.warning("slide_planner JSON 파싱 실패 → 슬라이드 0개. raw=%r", snippet)
            return {
                "deck_spec": spec.model_dump(),
                "slide_dsls": [],
                "issues": pre_issues + [Issue(
                    stage="parse", code="json",
                    message=f"planner output was not valid JSON. raw~ {snippet}",
                ).model_dump()],
            }

        # 3) Deterministic validation (keeps structurally-valid slides, reports the rest).
        slides, issues = validate_deck(raw)
        if not slides:
            logger.warning(
                "검증 통과 슬라이드 0개 → 렌더할 슬라이드 없음. issues=%s",
                [i.code for i in issues],
            )
        elif issues:
            logger.info(
                "검증 통과 슬라이드 %d개 · issue %d건: %s",
                len(slides), len(issues), [i.code for i in issues],
            )
        return {
            "deck_spec": spec.model_dump(),
            "slide_dsls": [s.model_dump() for s in slides],
            "issues": pre_issues + [i.model_dump() for i in issues],
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


async def render_node(state: PptState, config: RunnableConfig = None) -> dict:
    """Layout IR → .pptx via the Node sidecar, plus the artifact + user-facing message.

    Records a ``render_report`` (ok/job_file/error/stack/stderr) into the state delta so
    the TraceWriter can surface render diagnostics. On no-slides/failure, returns an
    apology message and no ``output_path`` so the supervisor ends the turn.
    """
    settings = get_settings()
    session_id = state.get("session_id") or "session"
    run_id = ((config or {}).get("configurable") or {}).get("trace_run_id") or uuid4().hex

    layout_irs = state.get("layout_irs", []) or []
    if not layout_irs:
        issues = list(state.get("issues", []) or [])
        issues.append(Issue(stage="render", code="no_slides",
                            message="no slides available to render").model_dump())
        reason = _fail_reason(issues)
        logger.warning("렌더할 슬라이드 없음(상류 단계 실패). reason=%s", reason)
        return {
            "issues": issues,
            "messages": [AIMessage(content=_fail_message(issues))],
            "render_report": {
                "attempted": False, "ok": False, "error": "no slides", "reason": reason,
            },
        }

    artifact_id = uuid4().hex
    out_path = os.path.join(settings.artifacts_dir, session_id, f"deck_{artifact_id}.pptx")
    job_dump_path = os.path.join(settings.artifacts_dir, session_id, f"render_job_{run_id}.json")
    result = await render_deck(
        layout_irs, state.get("theme") or resolve_theme(), out_path,
        settings.node_bin, job_dump_path=job_dump_path,
    )
    render_report = {
        "attempted": True,
        "ok": result.ok,
        "job_file": os.path.basename(job_dump_path),
        "slide_count": result.slide_count or len(layout_irs),
        "out_path": out_path,
        "error": result.error,
        "stack": result.stack,
        "stderr": result.stderr,
    }
    if not result.ok:
        logger.error(
            "render 실패: %s\nstack=%s\nstderr=%s",
            result.error, result.stack, result.stderr,
        )
        issues = list(state.get("issues", []) or [])
        issues.append(Issue(stage="render", code="render_failed",
                            message=result.error or "render failed").model_dump())
        render_report["reason"] = _fail_reason(issues)
        return {
            "issues": issues,
            "messages": [AIMessage(content=_fail_message(issues))],
            "render_report": render_report,
        }

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
        "render_report": render_report,
    }
