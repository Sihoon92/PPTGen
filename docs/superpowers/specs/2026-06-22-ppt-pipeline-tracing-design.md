# PPT 파이프라인 트레이싱 설계 — LLM 입출력 기록 & 렌더 에러 진단

- **날짜**: 2026-06-22
- **상태**: 설계 확정 (구현 계획 대기)
- **범위**: 백엔드 한정 (`backend/app/**`). 프론트엔드 변경 없음.

## 1. 배경 / 문제

PPT 생성 파이프라인은 `dsl → compiler → render` 순으로 동작한다(supervisor 허브 구조,
`backend/app/graph/nodes/ppt.py`). 현재 `dsl`(LLM)·`compiler`(결정론적)까지는 진행되는데
**`render` 단계(Node + PptxGenJS sidecar)에서 에러가 발생하고 원인 파악이 어렵다.**

기존 트레이싱(`backend/app/ppt/trace.py`의 `TraceWriter`)은 LangGraph `debug` 스트림을 듣고
노드별 **반환 상태(state delta)** 를 `<artifacts>/<session>/trace_*.json`에 저장한다. 그러나
진단에 필요한 정보 3가지가 빠져 있다:

1. **LLM 입력(프롬프트)이 기록되지 않음** — 트레이서는 노드의 반환 상태만 본다. `make_dsl_node`
   내부에서 만들어지는 실제 프롬프트(`DECK_SPEC_PROMPT`, catalog+deck_spec이 박힌
   `DSL_PLANNER_PROMPT`)는 상태에 올라가지 않아 기록되지 않는다. 게다가 `dsl` 노드 하나에
   **LLM 호출이 2회**(덱 기획 + 슬라이드 플래너)라 노드 단위로는 둘을 구분할 수 없다.
2. **LLM raw 응답이 기록되지 않음** — `extract_json` 이전의 원본 텍스트(`resp.content`)가
   버려진다. JSON 파싱이 깨지면 트레이스에는 `issues:[{code:"json"}]`만 남고 실제 출력이 사라진다.
3. **렌더 에러 원인이 반쪽만 남음** — `render_node`는 예외를 던지지 않고 실패를 `Issue`로 변환하므로
   트레이스 `status`가 `error`가 아니라 `done`이 된다. `render.mjs`는 `{error, stack}`을
   돌려주지만 `renderer.py`가 **`error`만 읽고 `stack`을 버리며**, 그나마 **500자로 잘린다**
   (`renderer.py:54-59`). 그리고 **렌더러에 넘긴 입력(job)이 저장되지 않아 단독 재현이 불가능**하다.

## 2. 목표 / 비목표

**목표**
- LLM 호출 **1회 = 1레코드**로 프롬프트·raw 응답·라벨·지연시간·토큰(가능 시)·에러를 기록.
- 렌더 단계의 **정확한 입력(job JSON) 보존** → `node render.mjs < render_job_*.json` 단독 재현.
- 렌더 **전체 에러 + JS 스택 + 전체 stderr** 보존(현 truncation/누락 제거).
- 노드 실패 시 트레이스 `status`를 `error`로 교정, run 전체 성공 여부(`ok`) 표시.
- 디스크 JSON 파일로 확인 가능(별도 UI/엔드포인트 신규 작업 없음).

**비목표 (YAGNI)**
- 프론트 디버그 UI 연동 (기존 `GET /sessions/{id}/trace`가 확장 스키마를 그대로 반환하므로 추가 작업 없음).
- 트레이스 파일 자동 보존/회전(N개 유지).
- 비밀정보 redaction (로컬 LLM·로컬 개발, 민감정보 없음).

## 3. 접근법 (선택: B)

LLM 입출력은 **노드의 반환 상태가 아니라 LLM 호출 경계에서만** 보인다. 또한 `PptState`는 SQLite
체크포인터 때문에 **JSON 직렬화가 가능해야** 하므로(`state.py` 주석) 레코더 객체를 상태에 실을 수 없다.

→ **LangChain 콜백 핸들러 + 렌더러 명시 계측**을 채택한다.
- 요청마다 `TracingCallbackHandler`를 그래프 `config["callbacks"]`에 붙여 **모든 LLM 호출을 자동 캡처**.
  run 상관관계와 노드명(`metadata.langgraph_node`)은 LangChain/LangGraph가 제공한다.
- 렌더는 LangChain 호출이 아니라 subprocess이므로 **렌더러를 직접 계측**한다.
- 기존 `TraceWriter`를 run의 단일 소유자로 두고 노드 이벤트 + LLM 호출 + 렌더 레코드를 한 파일에 병합.

검토했으나 탈락:
- **A. 노드 명시 계측**: 모든 노드를 건드려야 하고 미래 호출을 누락하기 쉬움.
- **C. 모델 래퍼(contextvar)**: 공유 모델을 감싸야 하고 contextvar의 태스크 경계 전파에 의존(취약),
  run 상관관계를 직접 구현해야 함.

## 4. 아키텍처 / 데이터 흐름

```
stream_graph (chat.py)
 ├─ run_id 1개 생성 (TraceWriter 소유)
 ├─ TraceWriter(run_id)                       # 기존: debug 스트림 → 노드 이벤트
 ├─ TracingCallbackHandler(tracer)            # 신규: 모든 LLM 호출 자동 캡처
 │     cfg["callbacks"] = [handler]
 ▼
 graph.astream(inputs, cfg, stream_mode=[...], subgraphs=True)
    ├─ dsl 노드:   model.ainvoke(msgs, config) ×2  → handler가 prompt+raw 기록
    ├─ compiler:   (LLM 없음)
    └─ render 노드: renderer가 job 덤프 + 전체 error/stack 반환 → render 레코드
 ▼
 finally: tracer.flush()  →  nodes + llm_calls + render 를 단일 JSON으로 저장
```

**구성요소**
1. **`TracingCallbackHandler`** (신규, `trace.py`): `AsyncCallbackHandler` 상속.
   - `on_chat_model_start(serialized, messages, *, run_id, metadata, **kw)`: 프롬프트 텍스트,
     `node = metadata.get("langgraph_node")`, `label = metadata.get("trace_label")`, 시작 ts를 버퍼.
   - `on_llm_end(LLMResult, *, run_id)`: raw 텍스트(`generations[0][0].text`), `token_usage`
     (`llm_output`에서 가능 시), 종료 ts → `tracer.llm_calls`에 확정 append.
   - `on_llm_error(error, *, run_id)`: 해당 레코드 `status="error"`, `error` 채움.
   - `run_id`로 start/end 짝맞춤. `tracer` 참조를 들고 직접 append.
2. **노드 시그니처 변경(미세)**: `async def dsl(state, config)` 로 `config` 수신 후
   `model.ainvoke(msgs, _label(config, "deck_spec"))` / `"slide_planner"`. supervisor의
   `_classify_intent`도 `"intent_classify"`. `_label`은 `config`에 `metadata={"trace_label": …}`만
   병합하는 1줄 헬퍼.
3. **렌더러 계측(`renderer.py`)**: spawn 직전에 `job`을 `render_job_<run>.json`으로 기록.
   `RenderResult`에 `stack`·`stderr` 추가, `err[:500]` truncation 제거, `result.get("stack")` 보존.
4. **병합 flush(`TraceWriter`)**: `llm_calls`·`render`·`backend`·`model`·`ok`·`ended_at` 필드 추가,
   render 노드 status 교정, 확장 스키마로 직렬화.

## 5. 데이터 스키마

run 하나당 트레이스 파일(`trace_<run>.json` / `trace_latest.json`):

```jsonc
{
  "session_id": "...", "run_id": "...", "title": "...",
  "started_at": "2026-06-22T14:03:01", "ended_at": "...",
  "backend": "ollama",            // ollama | internal
  "model": "gemma3n:e4b",
  "ok": false,                    // run 전체 성공 여부(렌더까지)

  "nodes": [                      // 기존 events
    {"node":"supervisor","status":"done","summary":"→ dsl"},
    {"node":"dsl","status":"done","summary":"제목:... · 슬라이드 5개","output":{...}},
    {"node":"compiler","status":"done","summary":"IR 5개"},
    {"node":"render","status":"error","summary":"렌더 실패"}   // status 교정
  ],

  "llm_calls": [                  // 신규: LLM 호출 1회 = 1레코드
    {
      "seq": 1,
      "node": "dsl",              // metadata.langgraph_node (자동)
      "label": "deck_spec",       // metadata.trace_label (우리가 부여)
      "model": "gemma3n:e4b",
      "started_at": "...", "ended_at": "...", "latency_ms": 842,
      "prompt": "<전체 프롬프트 원문, 미절단>",
      "raw_response": "<extract_json 전 LLM 원문, 미절단>",
      "token_usage": {"input": 0, "output": 0} | null,
      "status": "ok",            // ok | error
      "error": null
    }
    // seq:2 → node:"dsl", label:"slide_planner", ...
  ],

  "render": {                     // 신규: 렌더 진단
    "attempted": true,
    "ok": false,
    "job_file": "render_job_<run>.json",   // 정확한 입력(재현용) 포인터
    "slide_count": 5,
    "out_path": "artifacts/<session>/deck_<id>.pptx",
    "error": "<전체 에러 메시지>",
    "stack": "<JS 스택 트레이스 — 현재 버려지는 것>",
    "stderr": "<전체 stderr — 현재 500자로 잘리는 것>"
  }
}
```

방어 규칙: `prompt`/`raw_response`는 **truncation 안 함**(원문이 진단 목적). 단 호출당 ~256KB 상한만
두고 초과 시 말줄임 + 표식. `render.job_file`은 클 수 있어 별도 파일(인라인 안 함).

## 6. 디스크 레이아웃

```
artifacts/
├─ <session_id>/
│   ├─ trace_<run>.json          # (기존) 이제 nodes+llm_calls+render 포함
│   ├─ trace_latest.json         # (기존) /trace API가 읽는 파일
│   ├─ render_job_<run>.json     # ★신규: render.mjs stdin job 원본 (재현용)
│   └─ deck_<artifact>.pptx      # (기존) 성공 시 산출물
└─ traces/                       # (기존) 사람이 찾기 쉬운 평면 디렉터리
    ├─ 20260622-140301_<title>_<run6>.json
    └─ latest.json
```

`render_job_<run>.json`은 **렌더 시도 직전에** 기록하므로 크래시/행 시에도 입력이 남는다.
`trace_*.json`의 `render.job_file`이 이 파일명을 가리킨다.

## 7. 변경 파일 / 터치포인트

| 파일 | 변경 | 위험도 |
|---|---|---|
| `app/ppt/trace.py` | `TracingCallbackHandler` 신규 + 스키마 확장 + render status 교정 | 중 |
| `app/ppt/renderer.py` | job 덤프, `stack`/`stderr` 보존, truncation 제거 | 낮 |
| `app/graph/nodes/ppt_nodes/stages.py` | 노드 `config` 수신·전달, 라벨, render 레코드 | 중 |
| `app/graph/nodes/ppt_nodes/supervisor.py` | `_classify_intent` config·라벨 | 낮 |
| `app/api/chat.py` | cfg에 `callbacks` 추가, handler 생성 | 낮 |
| `app/ppt/node_renderer/render.mjs` | 변경 없음 (이미 `{error, stack}` 반환) | — |
| `backend/tests/` | 신규 테스트 | — |

## 8. 에러 처리 원칙

기존 철학 유지 — **트레이싱은 절대 사용자 응답을 깨지 않는다.** 콜백/job 덤프/flush는 모두
try/except로 감싸 실패해도 무시한다(기존 `flush()`의 `except: pass`와 동일). 노드가 어떤 LangGraph
경로에서 `config`를 못 받더라도 콜백이 미전파되면 `llm_calls`가 비는 것뿐, 파이프라인은 정상 동작한다.

## 9. 테스트 전략

1. **`TracingCallbackHandler` 단위**: 가짜 `on_chat_model_start`/`on_llm_end` 이벤트 →
   `prompt`+`raw_response` 든 레코드 1개, 라벨·node 채워짐 확인.
2. **`renderer.py`**: 의도적으로 실패하는 IR(또는 스텁 `render.mjs`)로 `stack`/`stderr` 보존 +
   `render_job_*.json` 생성 확인. truncation 없음 확인.
3. **`TraceWriter` render status 교정**: artifact 없음 + `render_failed` issue → `status=="error"`,
   최상위 `ok==false`.
4. **통합**: `dsl → compiler → render` 1회 실행 후 trace 파일에 `llm_calls`가 라벨 포함 정확히
   2개(dsl) 들어가고 `render` 섹션이 채워지는지.

## 10. 미해결/후속 (이번 범위 밖)

- 트레이스 파일 회전/보존 정책.
- 프론트 디버그 UI에서 `llm_calls`/`render` 가시화.
- 실패한 DSL에 대한 자가 수리(self-repair) 루프 배선(코드에 `DSL_REPAIR_PROMPT`·`has_errors`가
  정의돼 있으나 현재 미배선) — 이번 트레이스 정보가 그 설계의 입력이 될 수 있음.
