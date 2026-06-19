# PPTGen — LLM 채팅 프론트엔드 + LangGraph 백엔드 설계서

- **작성일:** 2026-06-19
- **범위:** 1차 결과물 = 프론트엔드 LLM 채팅이 동작하는 구조. PPT 생성은 스텁으로만 자리 확보.
- **상태:** 승인됨 (브레인스토밍 완료)

## 1. 목표와 비범위

### 목표 (v1)
- React 프론트엔드에서 로컬 Ollama(`gemma3n:e4b`)와 SSE 스트리밍 채팅이 동작한다.
- 대화는 세션 단위로 기록되고 백엔드 재시작 후에도 유지된다(SQLite 영속화).
- 상단 `chat`/`ppt` 모드 토글이 LangGraph의 `master` 노드 라우팅을 구동한다.
- 좌측 패널에서 Ollama 연결 테스트, 세션 추가/선택이 가능하다.
- 우측 artifacts 패널을 on/off 할 수 있다(내용은 플레이스홀더).
- Claude풍 베이지+주황 테마.

### 비범위 (이후 단계)
- 실제 PPT(PPTX) 생성 로직 및 ppt subgraph 상세 노드.
- artifacts 패널의 실제 콘텐츠 렌더링(코드블록/마크다운 연동).
- LLM 기반 자동 모드 라우팅.
- 인증/멀티유저, 배포 인프라, Playwright E2E.

## 2. 결정 사항 (브레인스토밍 합의)

| 항목 | 결정 | 비고 |
|---|---|---|
| 프론트엔드 | React + Vite + TypeScript + Tailwind | artifacts/세션/스트리밍 UI에 적합 |
| 백엔드 | FastAPI + LangGraph | LangGraph는 Python 고정 |
| LLM | 로컬 Ollama, `gemma3n:e4b` | "Gemma-e4b"의 실제 태그로 가정, env로 변경 가능 |
| LLM 연결 추상화 | `OLLAMA_BASE_URL`/`OLLAMA_API_KEY` env 슬롯 | 지금은 로컬, 향후 원격/클라우드 전환 대비 |
| 세션 저장 | SQLite (`AsyncSqliteSaver` + 세션 메타 테이블) | 재시작 후 대화 유지 |
| 스트리밍 | SSE (`graph.astream` + `StreamingResponse`) | Claude풍 토큰 스트리밍 |
| 그래프 라우팅 | 단일 그래프 + master 라우터 노드 (Approach A) | 모드 기반 결정적 분기 |
| v1 범위 | chat 동작 / ppt 스텁 / artifacts 셸+플레이스홀더 | |

## 3. 저장소 구조

```
PPTGen/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 앱, CORS, 라우터 등록, startup에서 DB/그래프 초기화
│   │   ├── config.py          # pydantic-settings 기반 환경설정
│   │   ├── llm.py             # get_chat_model(): Ollama 클라이언트 팩토리 (base_url/api_key 추상화)
│   │   ├── graph/
│   │   │   ├── state.py       # GraphState (TypedDict)
│   │   │   ├── builder.py     # build_graph(), AsyncSqliteSaver 컴파일
│   │   │   └── nodes/
│   │   │       ├── master.py  # 라우팅 함수 route_by_mode
│   │   │       ├── chat.py    # chat 노드 (LLM 호출/스트리밍)
│   │   │       └── ppt.py     # ppt 스텁 서브그래프
│   │   ├── api/
│   │   │   ├── health.py      # GET /api/health/ollama
│   │   │   ├── sessions.py    # 세션 CRUD
│   │   │   └── chat.py        # POST /api/sessions/{id}/chat (SSE)
│   │   └── db/
│   │       ├── database.py    # SQLite 연결/스키마 초기화 (aiosqlite)
│   │       └── sessions_repo.py  # 세션 메타 CRUD
│   ├── tests/                 # pytest
│   ├── pyproject.toml         # 또는 requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── main.tsx, App.tsx
│   │   ├── theme/             # Claude풍 테마 토큰 (tailwind.config에서 사용)
│   │   ├── components/
│   │   │   ├── Sidebar/       # NewSessionButton, OllamaTestButton, SessionList
│   │   │   ├── Chat/          # MessageList, MessageBubble, Composer, ModeToggle
│   │   │   └── Artifacts/     # ArtifactsPanel, ArtifactsToggle
│   │   ├── api/               # client.ts(fetch 래퍼), sse.ts(SSE 리더)
│   │   ├── store/             # zustand 스토어
│   │   └── types/             # 공유 타입
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── package.json
└── docs/superpowers/specs/
```

- 프론트(기본 5173) ↔ 백엔드(기본 8000): REST + SSE, CORS 허용.
- Ollama 통신은 백엔드만 수행 → API 키가 프론트에 노출되지 않는다.

## 4. LangGraph 설계 (Approach A)

### GraphState (`graph/state.py`)
```python
from typing import Annotated, Literal, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    mode: Literal["chat", "ppt"]
    session_id: str
```

### 노드와 엣지
```
START → master → (조건부 라우팅) ─→ chat → END
                                  └─→ ppt  → END
```

- **master** (`nodes/master.py`): 패스스루 노드 + 라우팅 함수.
  ```python
  def route_by_mode(state: GraphState) -> Literal["chat", "ppt"]:
      return state["mode"]
  ```
  지금은 `state["mode"]`로 결정적 분기. 향후 이 지점에 LLM 기반 의도 분류를 추가해 확장한다.
- **chat** (`nodes/chat.py`): `get_chat_model()`로 받은 `ChatOllama`를 messages로 호출. 토큰을 스트리밍하고 최종 `AIMessage`를 상태에 append.
- **ppt** (`nodes/ppt.py`): **스텁 서브그래프**. v1에서는 단일 노드가 고정 응답("PPT 생성 기능은 준비 중입니다.")을 `AIMessage`로 반환. 서브그래프(`StateGraph`)로 감싸 두어, 이후 노드 추가만으로 확장 가능.

### 체크포인터 / 영속화
- `AsyncSqliteSaver`(aiosqlite 기반) 사용, `thread_id = session_id`.
- 대화 히스토리는 그래프 상태로 영속화되어 **별도 메시지 테이블이 불필요**(단일 진실 공급원).
- 히스토리 복원: `graph.aget_state(config).values["messages"]`.

## 5. LLM 연결 추상화 (`app/llm.py`)

```python
def get_chat_model():
    # config에서 base_url, api_key(optional), model 읽음
    # ChatOllama(model=..., base_url=..., client_kwargs={"headers": {...}} if api_key)
    ...
```
- 지금은 로컬(`http://localhost:11434`)이라 api_key 없이 동작.
- `OLLAMA_API_KEY`가 설정되면 `Authorization: Bearer ...` 헤더를 붙여 원격/클라우드 엔드포인트로 전환 가능.
- 모델 태그는 `OLLAMA_MODEL` env로 주입(기본값 `gemma3n:e4b`).

## 6. API 계약

모델 가정: "Gemma-e4b" → Ollama 태그 `gemma3n:e4b` (env `OLLAMA_MODEL`로 변경 가능).

| 메서드 | 경로 | 요청/응답 |
|---|---|---|
| GET | `/api/health/ollama` | → `{ok: bool, models: string[], error?: string}` |
| GET | `/api/sessions` | → `Session[]` (id, title, mode, created_at, updated_at) |
| POST | `/api/sessions` | body `{title?}` → `Session` |
| PATCH | `/api/sessions/{id}` | body `{title}` → `Session` |
| DELETE | `/api/sessions/{id}` | 세션 메타 + 체크포인트 스레드 삭제 → `204` |
| GET | `/api/sessions/{id}/messages` | → `Message[]` (체크포인터에서 복원) |
| POST | `/api/sessions/{id}/chat` | body `{content, mode}` → **SSE 스트림** |

### SSE 이벤트 형식
- `event: token` / `data: {"delta": "..."}` — 토큰 청크
- `event: done` / `data: {"message_id": "..."}` — 완료
- `event: error` / `data: {"message": "..."}` — 중간 실패

### 채팅 처리 흐름
1. 프론트가 `{content, mode}`를 POST.
2. 백엔드가 GraphState 구성(`messages += HumanMessage(content)`, `mode`, `session_id`).
3. `graph.astream(..., stream_mode="messages")`로 chat 노드 LLM 토큰을 수신.
4. 각 토큰을 SSE `token` 이벤트로 yield, 종료 시 `done`.
5. 체크포인터가 상태를 자동 저장(영속화).

### 세션 제목
- v1: 첫 user 메시지 앞부분을 잘라 자동 생성(추가 LLM 호출 없음). PATCH로 수동 변경 가능.

## 7. 세션 저장 (SQLite)

- 파일 하나: `app.db` (경로는 `APP_DB_PATH` env).
- **세션 메타 테이블** `sessions`:
  - `id TEXT PRIMARY KEY` (uuid)
  - `title TEXT`
  - `mode TEXT DEFAULT 'chat'` (마지막 사용 모드)
  - `created_at`, `updated_at` (ISO8601 TEXT)
- **체크포인트 테이블**: `AsyncSqliteSaver`가 관리(`thread_id = session id`) → 메시지 히스토리 보관.
- 동시성: `aiosqlite`(async) + WAL 모드.

## 8. 프론트엔드 UI / 테마

### 레이아웃
```
┌─────────────────────────────────────────────────────┐
│ [Chat | PPT] 모드토글            [Artifacts ▢] 토글  │  상단바
├──────────┬──────────────────────────────┬───────────┤
│ + 새 세션 │                              │           │
│ ⦿ Ollama │      메시지 스레드            │ Artifacts │
│  테스트   │                              │  패널     │
│ ───────  │                              │ (on/off)  │
│ 세션1    │  ┌────────────────────────┐  │           │
│ 세션2    │  │ 입력창          [전송] │  │           │
└──────────┴──────────────────────────────┴───────────┘
```
- **좌측 패널:** 상단 `+ 새 세션` → 그 아래 Ollama 테스트 버튼(상태 점: 🟢연결 / 🔴실패 / ⚪미확인, 모델 목록 툴팁) → 세션 리스트.
- **상단바:** chat/ppt 모드 토글, artifacts on/off 버튼.
- **중앙:** 메시지 스레드 + 입력 컴포저.
- **우측:** artifacts 패널(슬라이드 in/out, v1 플레이스홀더).

### 테마 (Claude풍)
- 베이지 배경 `#F5F1EB` 계열 + 주황 액센트 `#D97757`(Claude 코랄) 계열.
- Tailwind 테마 토큰으로 정의해 한 곳에서 관리. 정확한 hex는 구현 중 미세조정.

### 상태 관리
- zustand 스토어: `sessions / activeSessionId / messages / mode / artifactsOpen / ollamaStatus`.
- SSE는 POST가 필요하므로 `EventSource` 대신 `fetch` + `ReadableStream` 리더로 수신.
- Ollama 테스트 버튼 → `GET /api/health/ollama` 호출 후 상태 점 갱신.

## 9. 에러 처리

- **Ollama 미연결:** health가 `ok:false`+원인 반환. 채팅 시 `error` 이벤트 → 프론트가 "Ollama 실행 / `OLLAMA_BASE_URL` 확인" 안내.
- **모델 미설치:** health가 모델 목록에서 `gemma3n:e4b` 부재 감지 → "`ollama pull gemma3n:e4b` 필요" 경고.
- **SSE 끊김:** 프론트가 리더 에러 처리, 해당 메시지를 "미완료"로 표시.
- **세션 없음:** `404`. 백엔드 예외는 구조화 JSON 에러로 반환.

## 10. 테스트 전략

원칙: **실제 Ollama 의존 없이** 목 기반으로 검증.

- **백엔드 (pytest):**
  - `route_by_mode` 단위테스트 (chat/ppt 분기).
  - ppt 스텁 노드 — 고정 응답 반환 검증.
  - 세션 repo CRUD — 임시 SQLite 사용.
  - 채팅 엔드포인트 — `get_chat_model`을 **가짜 스트리밍 LLM으로 monkeypatch** → SSE 이벤트(`token`/`done`) 검증.
  - health 엔드포인트 — Ollama 호출 목 처리(연결/실패/모델 부재).
- **프론트 (Vitest + React Testing Library):**
  - 사이드바 세션 렌더, 모드 토글, artifacts 토글 동작.
  - fetch/SSE 목.
- **범위 외:** Playwright E2E.

## 11. 환경설정 (`.env.example`)

```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_API_KEY=                 # 선택, 향후 원격/클라우드용
OLLAMA_MODEL=gemma3n:e4b
APP_DB_PATH=./app.db
CORS_ORIGINS=http://localhost:5173
```
- `config.py`는 pydantic-settings로 로드. 사용자가 `.env`에 직접 키를 추가할 수 있도록 설계.

## 12. 확장 지점 (다음 단계 연결고리)

- `master` 노드: mode 기반 분기 → LLM 자동 라우팅 추가.
- `ppt` 서브그래프: 단일 스텁 노드 → 다중 노드(아웃라인 생성 → 슬라이드 설계 → PPTX 빌드 등).
- artifacts 패널: 플레이스홀더 → 실제 PPTX 미리보기/마크다운/코드 렌더.
- LLM 연결: 로컬 → `OLLAMA_API_KEY` 기반 원격/클라우드.
