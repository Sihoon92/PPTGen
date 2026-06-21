# PPT Supervisor 재설계 (최소 골격) — 설계 문서

작성일: 2026-06-20
상태: 승인됨 (구현 착수)

## Context (왜)

현재 PPT 서브그래프는 노드가 10개(`deck_intent, deck_spec, dsl_planner, dsl_validator,
dsl_repair, theme_resolver, layout_compiler, renderer, content_qa, finalize`)로 과도하게
세분화돼 있어 흐름을 파악·수정하기 어렵다. 이를 **supervisor 허브 + 3개 스테이지 노드**로
단순화한다. 도메인 로직(`app/ppt/*.py`)은 그대로 재사용하고, 바뀌는 것은 **그래프 계층**뿐이다.

설계 결정(사용자 확정):
1. **허브형 supervisor** — 모든 노드는 끝나면 supervisor로 복귀, supervisor가 다음을 결정
2. **최소 골격** — `supervisor + dsl + compiler + render` 4개 노드. 검증·테마는 노드 내부로
   흡수. content QA / dsl repair / deck-intent 되묻기(`interrupt`)는 **다음 단계로 보류**
3. **기존 교체** — `ppt_nodes/`를 재구성(planning.py·pipeline.py 제거), `ppt.py` 교체,
   관련 테스트 재작성. `app/ppt/*.py`는 변경 없이 재사용
4. **상태(포인터)기반 전진 + 의도만 LLM** — 한 턴의 시작 스테이지만 결정하고 이후는 전진.
   기존 deck가 있는데 새 메시지가 오면 LLM이 시작 스테이지를 분류(편집). 미처리 메시지는
   `handled_msg_count`로 판별. 무한 루프는 `step_count`(MAX_STEPS=8)로 차단

## 그래프 위상

```
        ┌───────────────────────────┐
        ▼                           │
START → supervisor ─route─▶ dsl ────┤
            │      ─route─▶ compiler─┤  (각 노드 종료 후 supervisor 복귀)
            │      ─route─▶ render ──┘
            └──── route=end ─▶ END
```

- `START → supervisor`
- `supervisor`의 조건부 엣지: state `route` → `{dsl|compiler|render|END}`
- `dsl/compiler/render → supervisor` (단일 허브)
- 서브그래프는 체크포인터 없이 `compile()` (부모 그래프가 영속화 소유) — 현행 유지

## supervisor 판단 로직 (포인터 기반 전진)

```
STAGES = ["dsl", "compiler", "render"]

supervisor(state):
    step = step_count + 1
    if step > MAX_STEPS(8): return route="end"

    if human_msg_count(messages) > handled_msg_count:   # 새 사용자 턴
        start = classify_intent(LLM) if output_path else "dsl"   # 편집이면 LLM 분류
        i = STAGES.index(start)
        return route=start, pipeline_pos=i, handled_msg_count=humans, **reset_from(i)
    else:                                                # 같은 턴 내 전진
        nxt = pipeline_pos + 1
        return route="end" if nxt >= len(STAGES) else route=STAGES[nxt], pipeline_pos=nxt
```

- `pipeline_pos`는 턴마다 단조 증가 → **종료 보장**(스테이지당 최대 1회 실행)
- 신규 생성: 시작 `dsl` → 전진으로 compiler → render → end (LLM 분류 불필요)
- 편집(기존 deck + 새 메시지): LLM이 `dsl|compiler|render` 중 시작점 분류 후 전진.
  분류 실패 시 안전 폴백 `dsl`
- `reset_from(i)`: 시작 스테이지 이후 산출물 초기화 — `i≤0`이면 slide_dsls, `i≤1`이면
  layout_irs, 항상 output_path를 비워 재생성이 깨끗하게 진행

## 노드 책임 (도메인 로직 재사용)

| 노드 | 종류 | 입력 → 출력 | 내부 (재사용 모듈) |
|------|------|-------------|--------------------|
| `supervisor` | router | state → `{route, step_count, pipeline_pos, handled_msg_count}` | (LLM은 편집 분류 시만) |
| `dsl` | llm | brief → `{deck_spec, slide_dsls, issues}` | `prompts.DECK_SPEC_PROMPT`·`DSL_PLANNER_PROMPT`, `extract_json`, `DeckSpec`, `validator.validate_deck` |
| `compiler` | code | slide_dsls → `{theme, layout_irs}` | `theme.resolve_theme`, `compiler.compile_slide` |
| `render` | render(async) | layout_irs → `{output_path, artifact_id, artifact, messages}` 또는 실패 시 `{issues, messages}` | `renderer.render_deck` + finalize(artifact dict + AIMessage) |

- `dsl`이 기존 deck_spec + dsl_planner + dsl_validator 흡수
- `render`가 기존 renderer + finalize 흡수
- 보류: `interrupt` 되묻기, content_qa, dsl_repair

## State (`PptState` 슬림화)

```python
class PptState(TypedDict, total=False):
    # boundary (GraphState와 공유)
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    artifact: dict
    # pipeline
    deck_spec: dict
    slide_dsls: list[dict]
    layout_irs: list[dict]
    theme: dict
    output_path: str
    artifact_id: str
    issues: list[dict]
    # supervisor control
    route: str
    step_count: int
    pipeline_pos: int
    handled_msg_count: int
```

제거: `raw_deck, user_brief, repair_count, qa_count, pending_question`.

## 파일 변경

```
교체   app/graph/nodes/ppt.py            build_ppt_subgraph(supervisor 허브)
재구성 app/graph/nodes/ppt_nodes/
         삭제 planning.py, pipeline.py
         신규 supervisor.py  (supervisor 노드 + route_from_supervisor + 헬퍼)
         신규 stages.py      (dsl/compiler/render 노드 + _last_human)
수정   app/graph/state.py                PptState 슬림화
수정   app/ppt/prompts.py                SUPERVISOR_INTENT_PROMPT 추가
수정   app/ppt/trace.py                  NODE_META/_summary/_tool_for 새 4노드로
재작성 tests/test_ppt_node.py            새 노드 기준
재작성 tests/test_ppt_api.py             트레이스 노드명/인터럽트 테스트 갱신
신규   tests/test_ppt_supervisor.py      route_from_supervisor 단위 테스트
삭제   tests/test_ppt_interrupt.py       interrupt 제거로 폐기
재사용 app/ppt/{dsl,compiler,ir,renderer,theme,validator,extract,prompts}.py (불변)
```

## 에러 처리 / 트레이스 / 테스트

- **에러**: 각 노드는 예외 대신 `issues` 기록 후 진행(SSE 안 끊김). render 실패/슬라이드 없음 →
  output_path 미설정, render가 사과 메시지 반환, supervisor가 end로 종료
- **트레이스**: `NODE_META`를 `supervisor/dsl/compiler/render`로 교체. `_summary`는 노드별 요약
  (supervisor=`→ route`, dsl=제목·슬라이드 수, compiler=IR 수, render=파일명)
- **테스트**: ① supervisor 라우팅 단위(상태별 route), ② E2E 스모크(brief→pptx, fake model 2콜),
  ③ 비-JSON 우아한 실패(무한루프·StopIteration 없이 사과), ④ 트레이스 지속성 노드명 갱신

## Acceptance

1. 상세 brief → dsl→compiler→render→end로 .pptx 생성 (fake model 2콜로 종료)
2. 비-JSON 출력에도 무한 루프 없이 사과 메시지로 종료
3. `route_from_supervisor`가 상태별로 올바른 다음 노드 반환
4. 트레이스가 새 노드명으로 지속/스트리밍
5. 기존 도메인 로직(`app/ppt/*.py`) 변경 없이 재사용
```
