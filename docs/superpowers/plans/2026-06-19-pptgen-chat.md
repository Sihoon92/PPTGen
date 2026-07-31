# PPTGen Chat-First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude-style chat web app where a React frontend streams conversations from a local Ollama model through a LangGraph master-router backend, with persistent sessions and a stubbed PPT mode.

**Architecture:** FastAPI + LangGraph backend exposes REST + SSE. A single LangGraph graph has a `master` router that branches by `mode` to a `chat` node (real LLM) or a `ppt` stub subgraph. Conversation state persists in SQLite via `AsyncSqliteSaver` keyed by `session_id`. A React + Vite + Tailwind frontend renders a sidebar (sessions, Ollama test), a chat thread with chat/ppt toggle, and a toggleable artifacts panel.

**Tech Stack:** Python 3.11+, FastAPI, LangGraph, langchain-ollama (ChatOllama), AsyncSqliteSaver, aiosqlite, pydantic-settings, httpx, pytest/pytest-asyncio. React 18, Vite, TypeScript, Tailwind CSS v3, zustand, Vitest + React Testing Library.

## Global Constraints

- Python **3.11+**; Node **18+**.
- LLM model tag is configurable via env `OLLAMA_MODEL`, default **`gemma3n:e4b`**.
- LLM connection abstracted via env: `OLLAMA_BASE_URL` (default `http://localhost:11434`), `OLLAMA_API_KEY` (optional, empty by default).
- Ollama is reached **only from the backend** — the API key must never appear in frontend code or network calls.
- SQLite file path via env `APP_DB_PATH` (default `./app.db`).
- CORS origins via env `CORS_ORIGINS` (default `http://localhost:5173`).
- Theme: beige background `#F5F1EB`, orange accent `#D97757` (exact hexes may be fine-tuned but use these as tokens).
- All tests must pass **without a running Ollama instance** (mock/fake the LLM and HTTP calls).
- Tailwind pinned to **v3** (classic `tailwind.config.js` with theme tokens).
- SSE event names: `token` (`{"delta": "..."}`), `done` (`{"session_id": "..."}`), `error` (`{"message": "..."}`).

---

# Phase A — Backend

### Task 1: Backend scaffold + configuration

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py` (empty)
- Create: `backend/app/config.py`
- Create: `backend/tests/__init__.py` (empty)
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `app.config.Settings` (pydantic-settings) with fields `ollama_base_url: str`, `ollama_api_key: str`, `ollama_model: str`, `app_db_path: str`, `cors_origins: str`; and `get_settings() -> Settings` (cached).

- [ ] **Step 1: Create `backend/pyproject.toml`**

```toml
[project]
name = "pptgen-backend"
version = "0.1.0"
description = "PPTGen chat backend (FastAPI + LangGraph)"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "langgraph>=0.2.0",
    "langchain-core>=0.3.0",
    "langchain-ollama>=0.2.0",
    "langgraph-checkpoint-sqlite>=2.0.0",
    "aiosqlite>=0.20",
    "pydantic-settings>=2.3",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "anyio>=4.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]
```

- [ ] **Step 2: Create `backend/.env.example`**

```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_API_KEY=
OLLAMA_MODEL=gemma3n:e4b
APP_DB_PATH=./app.db
CORS_ORIGINS=http://localhost:5173
```

- [ ] **Step 3: Write the failing test** — `backend/tests/test_config.py`

```python
from app.config import Settings


def test_settings_defaults(monkeypatch):
    for key in ("OLLAMA_BASE_URL", "OLLAMA_API_KEY", "OLLAMA_MODEL", "APP_DB_PATH", "CORS_ORIGINS"):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.ollama_api_key == ""
    assert s.ollama_model == "gemma3n:e4b"
    assert s.app_db_path == "./app.db"


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "custom:tag")
    monkeypatch.setenv("OLLAMA_API_KEY", "secret")
    s = Settings(_env_file=None)
    assert s.ollama_model == "custom:tag"
    assert s.ollama_api_key == "secret"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 5: Create `backend/app/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    ollama_api_key: str = ""
    ollama_model: str = "gemma3n:e4b"
    app_db_path: str = "./app.db"
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Create `backend/tests/conftest.py`** (ensures `app` package is importable when running from `backend/`)

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 7: Install deps and run tests**

Run: `cd backend && pip install -e ".[dev]" && python -m pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/.env.example backend/app backend/tests
git commit -m "feat(backend): scaffold project and settings"
```

---

### Task 2: LLM client factory

**Files:**
- Create: `backend/app/llm.py`
- Test: `backend/tests/test_llm.py`

**Interfaces:**
- Consumes: `app.config.Settings`.
- Produces: `app.llm.get_chat_model(settings: Settings) -> BaseChatModel`. Builds `ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, ...)`. When `settings.ollama_api_key` is non-empty, attaches `Authorization: Bearer <key>` via `client_kwargs={"headers": {...}}`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_llm.py`

```python
from app.config import Settings
from app.llm import get_chat_model


def test_get_chat_model_uses_settings():
    s = Settings(_env_file=None, ollama_model="gemma3n:e4b",
                 ollama_base_url="http://localhost:11434", ollama_api_key="")
    model = get_chat_model(s)
    assert model.model == "gemma3n:e4b"
    assert "localhost:11434" in model.base_url


def test_get_chat_model_sets_auth_header_when_key_present():
    s = Settings(_env_file=None, ollama_api_key="secret-key")
    model = get_chat_model(s)
    headers = (model.client_kwargs or {}).get("headers", {})
    assert headers.get("Authorization") == "Bearer secret-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm'`

- [ ] **Step 3: Create `backend/app/llm.py`**

```python
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama

from app.config import Settings


def get_chat_model(settings: Settings) -> BaseChatModel:
    client_kwargs: dict = {}
    if settings.ollama_api_key:
        client_kwargs["headers"] = {"Authorization": f"Bearer {settings.ollama_api_key}"}
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        client_kwargs=client_kwargs or None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm.py backend/tests/test_llm.py
git commit -m "feat(backend): add Ollama chat model factory with optional auth header"
```

---

### Task 3: Graph state + master router

**Files:**
- Create: `backend/app/graph/__init__.py` (empty)
- Create: `backend/app/graph/state.py`
- Create: `backend/app/graph/nodes/__init__.py` (empty)
- Create: `backend/app/graph/nodes/master.py`
- Test: `backend/tests/test_master.py`

**Interfaces:**
- Produces: `app.graph.state.GraphState` (TypedDict with `messages`, `mode`, `session_id`); `app.graph.nodes.master.route_by_mode(state: GraphState) -> Literal["chat", "ppt"]`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_master.py`

```python
from app.graph.nodes.master import route_by_mode


def test_route_to_chat():
    assert route_by_mode({"mode": "chat", "messages": [], "session_id": "s1"}) == "chat"


def test_route_to_ppt():
    assert route_by_mode({"mode": "ppt", "messages": [], "session_id": "s1"}) == "ppt"


def test_route_defaults_to_chat_for_unknown():
    assert route_by_mode({"mode": "weird", "messages": [], "session_id": "s1"}) == "chat"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_master.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.graph'`

- [ ] **Step 3: Create `backend/app/graph/state.py`**

```python
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

Mode = Literal["chat", "ppt"]


class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    mode: Mode
    session_id: str
```

- [ ] **Step 4: Create `backend/app/graph/nodes/master.py`**

```python
from typing import Literal

from app.graph.state import GraphState


def route_by_mode(state: GraphState) -> Literal["chat", "ppt"]:
    """Master router: branch on the requested mode. Unknown modes fall back to chat.

    Extension point: replace/augment with LLM-based intent routing later.
    """
    return "ppt" if state.get("mode") == "ppt" else "chat"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_master.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph
git commit -m "feat(backend): add graph state and master router"
```

---

### Task 4: Chat node

**Files:**
- Create: `backend/app/graph/nodes/chat.py`
- Test: `backend/tests/test_chat_node.py`

**Interfaces:**
- Consumes: `GraphState`, `app.llm.get_chat_model`.
- Produces: `app.graph.nodes.chat.make_chat_node(model) -> Callable[[GraphState], Awaitable[dict]]`. The returned async node calls `model.ainvoke(state["messages"])` and returns `{"messages": [ai_message]}`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_chat_node.py`

```python
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import HumanMessage

from app.graph.nodes.chat import make_chat_node


@pytest.mark.asyncio
async def test_chat_node_appends_ai_message():
    fake = GenericFakeChatModel(messages=iter([("Hello there")]))
    node = make_chat_node(fake)
    out = await node({"messages": [HumanMessage("hi")], "mode": "chat", "session_id": "s1"})
    assert "messages" in out
    assert out["messages"][0].content == "Hello there"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_chat_node.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.graph.nodes.chat'`

- [ ] **Step 3: Create `backend/app/graph/nodes/chat.py`**

```python
from typing import Awaitable, Callable

from langchain_core.language_models import BaseChatModel

from app.graph.state import GraphState

ChatNode = Callable[[GraphState], Awaitable[dict]]


def make_chat_node(model: BaseChatModel) -> ChatNode:
    async def chat_node(state: GraphState) -> dict:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response]}

    return chat_node
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_chat_node.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/nodes/chat.py backend/tests/test_chat_node.py
git commit -m "feat(backend): add chat node"
```

---

### Task 5: PPT stub subgraph

**Files:**
- Create: `backend/app/graph/nodes/ppt.py`
- Test: `backend/tests/test_ppt_node.py`

**Interfaces:**
- Consumes: `GraphState`.
- Produces: `app.graph.nodes.ppt.PPT_STUB_MESSAGE: str`; `app.graph.nodes.ppt.build_ppt_subgraph() -> CompiledStateGraph`. The subgraph has a single node returning `{"messages": [AIMessage(PPT_STUB_MESSAGE)]}`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_ppt_node.py`

```python
import pytest
from langchain_core.messages import HumanMessage

from app.graph.nodes.ppt import PPT_STUB_MESSAGE, build_ppt_subgraph


@pytest.mark.asyncio
async def test_ppt_subgraph_returns_stub_message():
    graph = build_ppt_subgraph()
    out = await graph.ainvoke(
        {"messages": [HumanMessage("make slides")], "mode": "ppt", "session_id": "s1"}
    )
    assert out["messages"][-1].content == PPT_STUB_MESSAGE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_ppt_node.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.graph.nodes.ppt'`

- [ ] **Step 3: Create `backend/app/graph/nodes/ppt.py`**

```python
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from app.graph.state import GraphState

PPT_STUB_MESSAGE = (
    "PPT 생성 기능은 아직 준비 중입니다. 곧 슬라이드를 자동으로 만들어 드릴게요. "
    "지금은 'Chat' 모드에서 대화를 이어가실 수 있어요."
)


async def _ppt_stub_node(state: GraphState) -> dict:
    return {"messages": [AIMessage(content=PPT_STUB_MESSAGE)]}


def build_ppt_subgraph():
    """Single-node stub. Extension point: add outline -> design -> build nodes later."""
    sg = StateGraph(GraphState)
    sg.add_node("ppt_stub", _ppt_stub_node)
    sg.add_edge(START, "ppt_stub")
    sg.add_edge("ppt_stub", END)
    return sg.compile()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_ppt_node.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/nodes/ppt.py backend/tests/test_ppt_node.py
git commit -m "feat(backend): add ppt stub subgraph"
```

---

### Task 6: Graph builder + checkpointer wiring

**Files:**
- Create: `backend/app/graph/builder.py`
- Test: `backend/tests/test_builder.py`

**Interfaces:**
- Consumes: `GraphState`, `route_by_mode`, `make_chat_node`, `build_ppt_subgraph`.
- Produces: `app.graph.builder.build_graph(model, checkpointer) -> CompiledStateGraph`. Wires `START -> master -> conditional(chat|ppt) -> END`. `master` is a passthrough node; routing via `add_conditional_edges("master", route_by_mode, {"chat": "chat", "ppt": "ppt"})`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_builder.py`

```python
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
    graph = build_graph(_fake_model("second"), InMemorySaver())
    cfg = {"configurable": {"thread_id": "t3"}}
    await graph.ainvoke({"messages": [HumanMessage("first")], "mode": "chat", "session_id": "t3"}, cfg)
    snap = await graph.aget_state(cfg)
    assert len(snap.values["messages"]) >= 2  # human + ai
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.graph.builder'`

- [ ] **Step 3: Create `backend/app/graph/builder.py`**

```python
from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app.graph.nodes.chat import make_chat_node
from app.graph.nodes.master import route_by_mode
from app.graph.nodes.ppt import build_ppt_subgraph
from app.graph.state import GraphState


async def _master_node(state: GraphState) -> dict:
    """Passthrough router node. Actual branching happens in conditional edges."""
    return {}


def build_graph(model: BaseChatModel, checkpointer):
    sg = StateGraph(GraphState)
    sg.add_node("master", _master_node)
    sg.add_node("chat", make_chat_node(model))
    sg.add_node("ppt", build_ppt_subgraph())

    sg.add_edge(START, "master")
    sg.add_conditional_edges("master", route_by_mode, {"chat": "chat", "ppt": "ppt"})
    sg.add_edge("chat", END)
    sg.add_edge("ppt", END)

    return sg.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_builder.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/builder.py backend/tests/test_builder.py
git commit -m "feat(backend): wire master-router graph with checkpointer"
```

---

### Task 7: Session metadata store (SQLite)

**Files:**
- Create: `backend/app/db/__init__.py` (empty)
- Create: `backend/app/db/database.py`
- Create: `backend/app/db/sessions_repo.py`
- Test: `backend/tests/test_sessions_repo.py`

**Interfaces:**
- Produces:
  - `app.db.database.init_db(db_path: str) -> None` (creates `sessions` table if absent).
  - `app.db.sessions_repo` async functions, all taking `db_path: str`:
    - `create_session(db_path, title: str, mode: str = "chat") -> dict` → `{id, title, mode, created_at, updated_at}`
    - `list_sessions(db_path) -> list[dict]` (newest `updated_at` first)
    - `get_session(db_path, session_id) -> dict | None`
    - `rename_session(db_path, session_id, title) -> dict | None`
    - `touch_session(db_path, session_id) -> None` (updates `updated_at`)
    - `delete_session(db_path, session_id) -> bool`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_sessions_repo.py`

```python
import pytest

from app.db.database import init_db
from app.db import sessions_repo as repo


@pytest.fixture
async def db(tmp_path):
    path = str(tmp_path / "test.db")
    await init_db(path)
    return path


@pytest.mark.asyncio
async def test_create_and_get(db):
    s = await repo.create_session(db, title="First")
    assert s["title"] == "First"
    assert s["mode"] == "chat"
    fetched = await repo.get_session(db, s["id"])
    assert fetched["id"] == s["id"]


@pytest.mark.asyncio
async def test_list_orders_newest_first(db):
    a = await repo.create_session(db, title="A")
    b = await repo.create_session(db, title="B")
    await repo.touch_session(db, a["id"])  # bump A
    ids = [s["id"] for s in await repo.list_sessions(db)]
    assert ids[0] == a["id"]


@pytest.mark.asyncio
async def test_rename(db):
    s = await repo.create_session(db, title="Old")
    updated = await repo.rename_session(db, s["id"], "New")
    assert updated["title"] == "New"


@pytest.mark.asyncio
async def test_delete(db):
    s = await repo.create_session(db, title="X")
    assert await repo.delete_session(db, s["id"]) is True
    assert await repo.get_session(db, s["id"]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sessions_repo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db.database'`

- [ ] **Step 3: Create `backend/app/db/database.py`**

```python
import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'chat',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute(_SCHEMA)
        await conn.commit()
```

- [ ] **Step 4: Create `backend/app/db/sessions_repo.py`**

```python
import uuid
from datetime import datetime, timezone

import aiosqlite

_COLS = "id, title, mode, created_at, updated_at"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {"id": row[0], "title": row[1], "mode": row[2],
            "created_at": row[3], "updated_at": row[4]}


async def create_session(db_path: str, title: str, mode: str = "chat") -> dict:
    sid = str(uuid.uuid4())
    now = _now()
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            f"INSERT INTO sessions ({_COLS}) VALUES (?, ?, ?, ?, ?)",
            (sid, title, mode, now, now),
        )
        await conn.commit()
    return {"id": sid, "title": title, "mode": mode, "created_at": now, "updated_at": now}


async def list_sessions(db_path: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM sessions ORDER BY updated_at DESC"
        )
        rows = await cur.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_session(db_path: str, session_id: str) -> dict | None:
    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cur.fetchone()
    return _row_to_dict(row) if row else None


async def rename_session(db_path: str, session_id: str, title: str) -> dict | None:
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now(), session_id),
        )
        await conn.commit()
    return await get_session(db_path, session_id)


async def touch_session(db_path: str, session_id: str) -> None:
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (_now(), session_id)
        )
        await conn.commit()


async def delete_session(db_path: str, session_id: str) -> bool:
    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await conn.commit()
        return cur.rowcount > 0
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sessions_repo.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/db backend/tests/test_sessions_repo.py
git commit -m "feat(backend): add SQLite session metadata store"
```

---

### Task 8: App state, lifespan, and FastAPI app shell

**Files:**
- Create: `backend/app/state.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/test_app_root.py`

**Interfaces:**
- Produces:
  - `app.state.AppState` dataclass holding `graph`, `db_path`, `settings`, `checkpointer_cm`.
  - `app.main.create_app() -> FastAPI` with CORS, a `lifespan` that calls `init_db`, opens `AsyncSqliteSaver`, builds the graph via `build_graph`, and stores an `AppState` on `app.state.app_state`. Includes a `GET /` returning `{"status": "ok"}`.
  - `app.main.get_app_state(request) -> AppState` dependency.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_app_root.py`

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_root_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # trigger lifespan
        async with app.router.lifespan_context(app):
            resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_app_root.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Create `backend/app/state.py`**

```python
from dataclasses import dataclass
from typing import Any

from app.config import Settings


@dataclass
class AppState:
    graph: Any
    db_path: str
    settings: Settings
    checkpointer_cm: Any  # the AsyncSqliteSaver context manager (kept to close on shutdown)
```

- [ ] **Step 4: Create `backend/app/main.py`**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.config import get_settings
from app.db.database import init_db
from app.graph.builder import build_graph
from app.llm import get_chat_model
from app.state import AppState


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db(settings.app_db_path)

    cm = AsyncSqliteSaver.from_conn_string(settings.app_db_path)
    checkpointer = await cm.__aenter__()
    model = get_chat_model(settings)
    graph = build_graph(model, checkpointer)

    app.state.app_state = AppState(
        graph=graph, db_path=settings.app_db_path, settings=settings, checkpointer_cm=cm
    )
    try:
        yield
    finally:
        await cm.__aexit__(None, None, None)


def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PPTGen Backend", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root():
        return {"status": "ok"}

    # routers registered in later tasks
    from app.api import health, sessions, chat
    app.include_router(health.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")

    return app


app = create_app()
```

> NOTE: This imports `app.api.health/sessions/chat`, created in Tasks 9–11. To keep Task 8 independently runnable, create empty router stubs now:

- [ ] **Step 5: Create stub routers so the app imports**

Create `backend/app/api/__init__.py` (empty), and three files each containing:

`backend/app/api/health.py`:
```python
from fastapi import APIRouter

router = APIRouter()
```
`backend/app/api/sessions.py`:
```python
from fastapi import APIRouter

router = APIRouter()
```
`backend/app/api/chat.py`:
```python
from fastapi import APIRouter

router = APIRouter()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_app_root.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Commit**

```bash
git add backend/app/state.py backend/app/main.py backend/app/api backend/tests/test_app_root.py
git commit -m "feat(backend): add app shell, lifespan, and checkpointer wiring"
```

---

### Task 9: Health endpoint (Ollama connection test)

**Files:**
- Modify: `backend/app/api/health.py`
- Create: `backend/app/services/__init__.py` (empty)
- Create: `backend/app/services/ollama_health.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Consumes: `Settings`, `get_app_state`.
- Produces:
  - `app.services.ollama_health.check_ollama(settings) -> dict` → `{"ok": bool, "models": list[str], "error": str | None}`. Calls `GET {base_url}/api/tags` via httpx; on success extracts model names; on connection error returns `ok=False` with an error string.
  - `GET /api/health/ollama` returning that dict.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_health.py`

```python
import httpx
import pytest

from app.config import Settings
from app.services.ollama_health import check_ollama


@pytest.mark.asyncio
async def test_check_ollama_success(monkeypatch):
    async def fake_get(self, url, *a, **k):
        return httpx.Response(200, json={"models": [{"name": "gemma3n:e4b"}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    result = await check_ollama(Settings(_env_file=None))
    assert result["ok"] is True
    assert "gemma3n:e4b" in result["models"]
    assert result["error"] is None


@pytest.mark.asyncio
async def test_check_ollama_connection_error(monkeypatch):
    async def fake_get(self, url, *a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    result = await check_ollama(Settings(_env_file=None))
    assert result["ok"] is False
    assert result["models"] == []
    assert "refused" in result["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.ollama_health'`

- [ ] **Step 3: Create `backend/app/services/ollama_health.py`**

```python
import httpx

from app.config import Settings


async def check_ollama(settings: Settings) -> dict:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    headers = {}
    if settings.ollama_api_key:
        headers["Authorization"] = f"Bearer {settings.ollama_api_key}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        models = [m.get("name", "") for m in data.get("models", [])]
        return {"ok": True, "models": models, "error": None}
    except Exception as exc:  # noqa: BLE001 - surface any connectivity problem to the UI
        return {"ok": False, "models": [], "error": str(exc)}
```

- [ ] **Step 4: Replace `backend/app/api/health.py`**

```python
from fastapi import APIRouter, Depends

from app.main import get_app_state
from app.services.ollama_health import check_ollama
from app.state import AppState

router = APIRouter()


@router.get("/health/ollama")
async def health_ollama(state: AppState = Depends(get_app_state)):
    return await check_ollama(state.settings)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_health.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services backend/app/api/health.py backend/tests/test_health.py
git commit -m "feat(backend): add Ollama health check endpoint"
```

---

### Task 10: Sessions endpoints

**Files:**
- Modify: `backend/app/api/sessions.py`
- Create: `backend/app/schemas.py`
- Test: `backend/tests/test_sessions_api.py`

**Interfaces:**
- Consumes: `sessions_repo`, `get_app_state`, graph for history/deletion.
- Produces (all under `/api`):
  - `POST /sessions` body `{title?: str}` → 201 session dict.
  - `GET /sessions` → list of session dicts.
  - `PATCH /sessions/{id}` body `{title: str}` → session dict (404 if missing).
  - `DELETE /sessions/{id}` → 204 (404 if missing).
  - `GET /sessions/{id}/messages` → `{"messages": [{"role": "user"|"assistant", "content": str}]}` from checkpointer state.
  - `app.schemas`: `CreateSessionBody{title: str | None}`, `RenameBody{title: str}`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_sessions_api.py`

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    app = create_app()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
async def test_create_and_list_session(client):
    r = await client.post("/api/sessions", json={"title": "Hello"})
    assert r.status_code == 201
    sid = r.json()["id"]
    r2 = await client.get("/api/sessions")
    assert any(s["id"] == sid for s in r2.json())


@pytest.mark.asyncio
async def test_rename_and_delete(client):
    sid = (await client.post("/api/sessions", json={})).json()["id"]
    r = await client.patch(f"/api/sessions/{sid}", json={"title": "Renamed"})
    assert r.json()["title"] == "Renamed"
    assert (await client.delete(f"/api/sessions/{sid}")).status_code == 204
    assert (await client.patch(f"/api/sessions/{sid}", json={"title": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_messages_empty_for_new_session(client):
    sid = (await client.post("/api/sessions", json={})).json()["id"]
    r = await client.get(f"/api/sessions/{sid}/messages")
    assert r.status_code == 200
    assert r.json()["messages"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sessions_api.py -v`
Expected: FAIL (404s / missing routes)

- [ ] **Step 3: Create `backend/app/schemas.py`**

```python
from pydantic import BaseModel


class CreateSessionBody(BaseModel):
    title: str | None = None


class RenameBody(BaseModel):
    title: str


class ChatBody(BaseModel):
    content: str
    mode: str = "chat"
```

- [ ] **Step 4: Create `backend/app/api/messages_util.py`** (shared message serialization)

```python
from langchain_core.messages import AIMessage, HumanMessage


def serialize_messages(messages: list) -> list[dict]:
    out = []
    for m in messages:
        if isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        else:
            role = "system"
        content = m.content if isinstance(m.content, str) else str(m.content)
        out.append({"role": role, "content": content})
    return out


async def load_history(graph, session_id: str) -> list[dict]:
    cfg = {"configurable": {"thread_id": session_id}}
    snap = await graph.aget_state(cfg)
    messages = (snap.values or {}).get("messages", []) if snap else []
    return serialize_messages(messages)
```

- [ ] **Step 5: Replace `backend/app/api/sessions.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.messages_util import load_history
from app.db import sessions_repo as repo
from app.main import get_app_state
from app.schemas import CreateSessionBody, RenameBody
from app.state import AppState

router = APIRouter()


@router.post("/sessions", status_code=201)
async def create_session(body: CreateSessionBody, state: AppState = Depends(get_app_state)):
    title = body.title or "New chat"
    return await repo.create_session(state.db_path, title=title)


@router.get("/sessions")
async def list_sessions(state: AppState = Depends(get_app_state)):
    return await repo.list_sessions(state.db_path)


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, body: RenameBody, state: AppState = Depends(get_app_state)):
    updated = await repo.rename_session(state.db_path, session_id, body.title)
    if updated is None:
        raise HTTPException(status_code=404, detail="session not found")
    return updated


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, state: AppState = Depends(get_app_state)):
    deleted = await repo.delete_session(state.db_path, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="session not found")
    return Response(status_code=204)


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, state: AppState = Depends(get_app_state)):
    session = await repo.get_session(state.db_path, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"messages": await load_history(state.graph, session_id)}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sessions_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/api/sessions.py backend/app/api/messages_util.py backend/tests/test_sessions_api.py
git commit -m "feat(backend): add session CRUD and history endpoints"
```

---

### Task 11: Chat SSE endpoint

**Files:**
- Modify: `backend/app/api/chat.py`
- Create: `backend/app/api/sse.py`
- Test: `backend/tests/test_chat_api.py`

**Interfaces:**
- Consumes: graph, `sessions_repo`, `ChatBody`.
- Produces:
  - `app.api.sse.format_sse(event: str, data: dict) -> str` → `"event: <event>\ndata: <json>\n\n"`.
  - `POST /api/sessions/{id}/chat` body `{content, mode}` → `text/event-stream`. Streams `token` events (deltas) then `done`; on error streams `error`. Auto-titles a session from the first user message when its title is still the default `New chat`. Updates `updated_at`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_chat_api.py`

```python
import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

import app.main as main_mod
from app.main import create_app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))

    # Force the graph to use a deterministic fake streaming model.
    real_build = main_mod.build_graph

    def fake_build(model, checkpointer):
        fake = GenericFakeChatModel(messages=iter(["Hello world"]))
        return real_build(fake, checkpointer)

    monkeypatch.setattr(main_mod, "build_graph", fake_build)

    app = create_app()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.mark.asyncio
async def test_chat_streams_tokens_and_done(client):
    sid = (await client.post("/api/sessions", json={})).json()["id"]
    async with client.stream(
        "POST", f"/api/sessions/{sid}/chat", json={"content": "hi", "mode": "chat"}
    ) as resp:
        assert resp.status_code == 200
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk
    assert "event: token" in body
    assert "event: done" in body
    assert "Hello" in body


@pytest.mark.asyncio
async def test_chat_ppt_mode_streams_stub(client):
    sid = (await client.post("/api/sessions", json={})).json()["id"]
    async with client.stream(
        "POST", f"/api/sessions/{sid}/chat", json={"content": "slides", "mode": "ppt"}
    ) as resp:
        body = "".join([c async for c in resp.aiter_text()])
    assert "event: token" in body
    assert "준비 중" in body
    assert "event: done" in body


@pytest.mark.asyncio
async def test_chat_autotitles_session(client):
    sid = (await client.post("/api/sessions", json={})).json()["id"]
    async with client.stream(
        "POST", f"/api/sessions/{sid}/chat",
        json={"content": "Tell me about pandas", "mode": "chat"},
    ) as resp:
        _ = [c async for c in resp.aiter_text()]
    sessions = (await client.get("/api/sessions")).json()
    title = next(s["title"] for s in sessions if s["id"] == sid)
    assert title != "New chat"
    assert "pandas" in title.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_chat_api.py -v`
Expected: FAIL (route missing / 404)

- [ ] **Step 3: Create `backend/app/api/sse.py`**

```python
import json


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

- [ ] **Step 4: Replace `backend/app/api/chat.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from app.api.sse import format_sse
from app.db import sessions_repo as repo
from app.main import get_app_state
from app.schemas import ChatBody
from app.state import AppState

router = APIRouter()

_DEFAULT_TITLE = "New chat"


def _derive_title(text: str) -> str:
    text = text.strip().replace("\n", " ")
    return (text[:40] + "…") if len(text) > 40 else (text or _DEFAULT_TITLE)


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, body: ChatBody, state: AppState = Depends(get_app_state)):
    session = await repo.get_session(state.db_path, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    if session["title"] == _DEFAULT_TITLE:
        await repo.rename_session(state.db_path, session_id, _derive_title(body.content))
    else:
        await repo.touch_session(state.db_path, session_id)

    graph = state.graph
    cfg = {"configurable": {"thread_id": session_id}}
    inputs = {
        "messages": [HumanMessage(content=body.content)],
        "mode": body.mode,
        "session_id": session_id,
    }

    async def event_stream():
        streamed_nodes: set[str] = set()
        try:
            async for stream_mode, data in graph.astream(
                inputs, cfg, stream_mode=["messages", "updates"]
            ):
                if stream_mode == "messages":
                    chunk, meta = data
                    text = getattr(chunk, "content", "")
                    if text:
                        streamed_nodes.add(meta.get("langgraph_node", ""))
                        yield format_sse("token", {"delta": text})
                elif stream_mode == "updates":
                    for node, node_out in (data or {}).items():
                        if node in streamed_nodes:
                            continue
                        for m in (node_out or {}).get("messages", []) or []:
                            content = getattr(m, "content", "")
                            if content:
                                yield format_sse("token", {"delta": content})
            yield format_sse("done", {"session_id": session_id})
        except Exception as exc:  # noqa: BLE001 - report streaming failures to the client
            yield format_sse("error", {"message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_chat_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS (all tasks' tests green)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/chat.py backend/app/api/sse.py backend/tests/test_chat_api.py
git commit -m "feat(backend): add chat SSE endpoint with auto-titling"
```

---

# Phase B — Frontend

### Task 12: Frontend scaffold + Claude theme

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`
- Create: `frontend/tailwind.config.js`, `frontend/postcss.config.js`
- Create: `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/index.css`, `frontend/src/App.tsx`
- Create: `frontend/src/vite-env.d.ts`
- Create: `frontend/vitest.config.ts`, `frontend/src/test/setup.ts`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Produces: a Vite React app whose Tailwind theme exposes `bg-paper` (`#F5F1EB`) and `text-accent`/`bg-accent` (`#D97757`); `App` renders a shell with a recognizable title.

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "pptgen-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "zustand": "^4.5.5"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.8",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.20",
    "jsdom": "^25.0.0",
    "postcss": "^8.4.45",
    "tailwindcss": "^3.4.10",
    "typescript": "^5.5.4",
    "vite": "^5.4.3",
    "vitest": "^2.0.5"
  }
}
```

- [ ] **Step 2: Create config files**

`frontend/vite.config.ts`:
```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
```

`frontend/vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`frontend/tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts", "vitest.config.ts"]
}
```

`frontend/tailwind.config.js`:
```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F5F1EB",
        "paper-dark": "#EDE7DD",
        accent: "#D97757",
        "accent-dark": "#C2614A",
        ink: "#3D3A34",
      },
    },
  },
  plugins: [],
};
```

`frontend/postcss.config.js`:
```javascript
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
```

- [ ] **Step 3: Create app entry files**

`frontend/index.html`:
```html
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>PPTGen</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

`frontend/src/vite-env.d.ts`:
```typescript
/// <reference types="vite/client" />
```

`frontend/src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

`frontend/src/App.tsx`:
```tsx
export default function App() {
  return (
    <div className="h-screen bg-paper text-ink">
      <h1 className="sr-only">PPTGen</h1>
    </div>
  );
}
```

`frontend/src/test/setup.ts`:
```typescript
import "@testing-library/jest-dom";
```

- [ ] **Step 4: Write the failing test** — `frontend/src/App.test.tsx`

```tsx
import { render } from "@testing-library/react";
import App from "./App";

test("renders app shell with paper background", () => {
  const { container } = render(<App />);
  const root = container.firstChild as HTMLElement;
  expect(root.className).toContain("bg-paper");
});
```

- [ ] **Step 5: Install deps and run test**

Run: `cd frontend && npm install && npm test`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(frontend): scaffold Vite React app with Claude theme tokens"
```

---

### Task 13: Types + API client + SSE client

**Files:**
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/sse.ts`
- Test: `frontend/src/api/client.test.ts`
- Test: `frontend/src/api/sse.test.ts`

**Interfaces:**
- Produces:
  - `types`: `Session{id,title,mode,created_at,updated_at}`, `ChatMessage{role:"user"|"assistant"|"system",content:string}`, `OllamaHealth{ok:boolean,models:string[],error:string|null}`, `Mode="chat"|"ppt"`.
  - `api/client.ts`: `listSessions()`, `createSession(title?)`, `renameSession(id,title)`, `deleteSession(id)`, `getMessages(id)`, `checkOllama()`. All using `fetch` against `/api`.
  - `api/sse.ts`: `streamChat(sessionId, content, mode, handlers)` where `handlers = { onToken(delta), onDone(), onError(msg) }`. Parses the SSE byte stream from a POST `fetch`.

- [ ] **Step 1: Write the failing test** — `frontend/src/api/client.test.ts`

```typescript
import { afterEach, expect, test, vi } from "vitest";
import { createSession, listSessions, checkOllama } from "./client";

afterEach(() => vi.restoreAllMocks());

test("listSessions GETs /api/sessions", async () => {
  const data = [{ id: "1", title: "A", mode: "chat", created_at: "", updated_at: "" }];
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => data }));
  expect(await listSessions()).toEqual(data);
  expect(fetch).toHaveBeenCalledWith("/api/sessions", expect.objectContaining({ method: "GET" }));
});

test("createSession POSTs title", async () => {
  const session = { id: "2", title: "X", mode: "chat", created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => session }));
  expect(await createSession("X")).toEqual(session);
  const [, opts] = (fetch as any).mock.calls[0];
  expect(opts.method).toBe("POST");
  expect(JSON.parse(opts.body)).toEqual({ title: "X" });
});

test("checkOllama returns health", async () => {
  const health = { ok: true, models: ["gemma3n:e4b"], error: null };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => health }));
  expect(await checkOllama()).toEqual(health);
});
```

- [ ] **Step 2: Write the failing test** — `frontend/src/api/sse.test.ts`

```typescript
import { expect, test, vi } from "vitest";
import { streamChat } from "./sse";

function streamFromString(s: string): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(s);
  return new ReadableStream({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    },
  });
}

test("streamChat parses token and done events", async () => {
  const sse =
    'event: token\ndata: {"delta": "Hel"}\n\n' +
    'event: token\ndata: {"delta": "lo"}\n\n' +
    'event: done\ndata: {"session_id": "s1"}\n\n';
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body: streamFromString(sse) }));

  const tokens: string[] = [];
  let done = false;
  await streamChat("s1", "hi", "chat", {
    onToken: (d) => tokens.push(d),
    onDone: () => (done = true),
    onError: () => {},
  });
  expect(tokens.join("")).toBe("Hello");
  expect(done).toBe(true);
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL (cannot resolve `./client` / `./sse`)

- [ ] **Step 4: Create `frontend/src/types/index.ts`**

```typescript
export type Mode = "chat" | "ppt";

export interface Session {
  id: string;
  title: string;
  mode: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface OllamaHealth {
  ok: boolean;
  models: string[];
  error: string | null;
}
```

- [ ] **Step 5: Create `frontend/src/api/client.ts`**

```typescript
import type { ChatMessage, OllamaHealth, Session } from "../types";

const BASE = "/api";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export function listSessions(): Promise<Session[]> {
  return fetch(`${BASE}/sessions`, { method: "GET" }).then(json<Session[]>);
}

export function createSession(title?: string): Promise<Session> {
  return fetch(`${BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title ?? null }),
  }).then(json<Session>);
}

export function renameSession(id: string, title: string): Promise<Session> {
  return fetch(`${BASE}/sessions/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  }).then(json<Session>);
}

export async function deleteSession(id: string): Promise<void> {
  const res = await fetch(`${BASE}/sessions/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export function getMessages(id: string): Promise<{ messages: ChatMessage[] }> {
  return fetch(`${BASE}/sessions/${id}/messages`, { method: "GET" }).then(
    json<{ messages: ChatMessage[] }>,
  );
}

export function checkOllama(): Promise<OllamaHealth> {
  return fetch(`${BASE}/health/ollama`, { method: "GET" }).then(json<OllamaHealth>);
}
```

- [ ] **Step 6: Create `frontend/src/api/sse.ts`**

```typescript
import type { Mode } from "../types";

export interface StreamHandlers {
  onToken: (delta: string) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

export async function streamChat(
  sessionId: string,
  content: string,
  mode: Mode,
  handlers: StreamHandlers,
): Promise<void> {
  const res = await fetch(`/api/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, mode }),
  });
  if (!res.ok || !res.body) {
    handlers.onError(`HTTP ${res.status}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const event = /event: (.*)/.exec(raw)?.[1]?.trim();
      const dataLine = /data: (.*)/.exec(raw)?.[1] ?? "{}";
      const data = JSON.parse(dataLine);
      if (event === "token") handlers.onToken(data.delta ?? "");
      else if (event === "done") handlers.onDone();
      else if (event === "error") handlers.onError(data.message ?? "unknown error");
    }
  }
}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS (client + sse tests green)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types frontend/src/api
git commit -m "feat(frontend): add types, REST client, and SSE parser"
```

---

### Task 14: Zustand store

**Files:**
- Create: `frontend/src/store/store.ts`
- Test: `frontend/src/store/store.test.ts`

**Interfaces:**
- Produces: `useStore` zustand hook with state `{ sessions: Session[], activeSessionId: string|null, messages: ChatMessage[], mode: Mode, artifactsOpen: boolean, ollama: OllamaHealth|null, streaming: boolean }` and actions `setSessions`, `setActiveSession(id)`, `setMessages`, `appendUserMessage(content)`, `startAssistantMessage()`, `appendAssistantDelta(delta)`, `setMode(mode)`, `toggleArtifacts()`, `setOllama(health)`, `setStreaming(bool)`.

- [ ] **Step 1: Write the failing test** — `frontend/src/store/store.test.ts`

```typescript
import { beforeEach, expect, test } from "vitest";
import { useStore } from "./store";

beforeEach(() => {
  useStore.setState({
    sessions: [], activeSessionId: null, messages: [],
    mode: "chat", artifactsOpen: false, ollama: null, streaming: false,
  });
});

test("appendUserMessage adds a user message", () => {
  useStore.getState().appendUserMessage("hi");
  expect(useStore.getState().messages).toEqual([{ role: "user", content: "hi" }]);
});

test("assistant streaming accumulates deltas", () => {
  const s = useStore.getState();
  s.startAssistantMessage();
  s.appendAssistantDelta("He");
  s.appendAssistantDelta("llo");
  const msgs = useStore.getState().messages;
  expect(msgs[msgs.length - 1]).toEqual({ role: "assistant", content: "Hello" });
});

test("toggleArtifacts flips the flag", () => {
  useStore.getState().toggleArtifacts();
  expect(useStore.getState().artifactsOpen).toBe(true);
});

test("setMode updates mode", () => {
  useStore.getState().setMode("ppt");
  expect(useStore.getState().mode).toBe("ppt");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test src/store/store.test.ts`
Expected: FAIL (cannot resolve `./store`)

- [ ] **Step 3: Create `frontend/src/store/store.ts`**

```typescript
import { create } from "zustand";
import type { ChatMessage, Mode, OllamaHealth, Session } from "../types";

interface State {
  sessions: Session[];
  activeSessionId: string | null;
  messages: ChatMessage[];
  mode: Mode;
  artifactsOpen: boolean;
  ollama: OllamaHealth | null;
  streaming: boolean;

  setSessions: (s: Session[]) => void;
  setActiveSession: (id: string | null) => void;
  setMessages: (m: ChatMessage[]) => void;
  appendUserMessage: (content: string) => void;
  startAssistantMessage: () => void;
  appendAssistantDelta: (delta: string) => void;
  setMode: (mode: Mode) => void;
  toggleArtifacts: () => void;
  setOllama: (health: OllamaHealth) => void;
  setStreaming: (v: boolean) => void;
}

export const useStore = create<State>((set) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  mode: "chat",
  artifactsOpen: false,
  ollama: null,
  streaming: false,

  setSessions: (sessions) => set({ sessions }),
  setActiveSession: (activeSessionId) => set({ activeSessionId }),
  setMessages: (messages) => set({ messages }),
  appendUserMessage: (content) =>
    set((s) => ({ messages: [...s.messages, { role: "user", content }] })),
  startAssistantMessage: () =>
    set((s) => ({ messages: [...s.messages, { role: "assistant", content: "" }] })),
  appendAssistantDelta: (delta) =>
    set((s) => {
      const messages = s.messages.slice();
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        messages[messages.length - 1] = { ...last, content: last.content + delta };
      }
      return { messages };
    }),
  setMode: (mode) => set({ mode }),
  toggleArtifacts: () => set((s) => ({ artifactsOpen: !s.artifactsOpen })),
  setOllama: (ollama) => set({ ollama }),
  setStreaming: (streaming) => set({ streaming }),
}));
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test src/store/store.test.ts`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store
git commit -m "feat(frontend): add zustand app store"
```

---

### Task 15: Sidebar (sessions + Ollama test)

**Files:**
- Create: `frontend/src/components/Sidebar/OllamaTestButton.tsx`
- Create: `frontend/src/components/Sidebar/SessionList.tsx`
- Create: `frontend/src/components/Sidebar/Sidebar.tsx`
- Test: `frontend/src/components/Sidebar/Sidebar.test.tsx`

**Interfaces:**
- Consumes: `useStore`, `api/client`.
- Produces:
  - `OllamaTestButton`: button labeled "Ollama 연결 테스트"; on click calls `checkOllama()`, stores result, renders a status dot with `data-testid="ollama-status"` whose class reflects ok/fail (`bg-green-500` / `bg-red-500`) or unknown (`bg-gray-400`).
  - `SessionList`: renders sessions; clicking one calls `onSelect(id)`; active session highlighted with `bg-paper-dark`.
  - `Sidebar`: top "+ 새 세션" button (calls `createSession` then refreshes list and selects it), then `OllamaTestButton`, then `SessionList`. Loads sessions on mount.

- [ ] **Step 1: Write the failing test** — `frontend/src/components/Sidebar/Sidebar.test.tsx`

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import Sidebar from "./Sidebar";
import { useStore } from "../../store/store";
import * as client from "../../api/client";

afterEach(() => {
  vi.restoreAllMocks();
  useStore.setState({ sessions: [], activeSessionId: null });
});

test("loads and renders sessions on mount", async () => {
  vi.spyOn(client, "listSessions").mockResolvedValue([
    { id: "1", title: "Alpha", mode: "chat", created_at: "", updated_at: "" },
  ]);
  render(<Sidebar />);
  expect(await screen.findByText("Alpha")).toBeInTheDocument();
});

test("new session button creates and selects a session", async () => {
  vi.spyOn(client, "listSessions").mockResolvedValue([]);
  vi.spyOn(client, "createSession").mockResolvedValue({
    id: "new", title: "New chat", mode: "chat", created_at: "", updated_at: "",
  });
  render(<Sidebar />);
  await userEvent.click(screen.getByRole("button", { name: /새 세션/ }));
  await waitFor(() => expect(useStore.getState().activeSessionId).toBe("new"));
});

test("ollama test button shows green dot on success", async () => {
  vi.spyOn(client, "listSessions").mockResolvedValue([]);
  vi.spyOn(client, "checkOllama").mockResolvedValue({ ok: true, models: ["gemma3n:e4b"], error: null });
  render(<Sidebar />);
  await userEvent.click(screen.getByRole("button", { name: /Ollama 연결 테스트/ }));
  await waitFor(() =>
    expect(screen.getByTestId("ollama-status").className).toContain("bg-green-500"),
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test src/components/Sidebar`
Expected: FAIL (cannot resolve `./Sidebar`)

- [ ] **Step 3: Create `frontend/src/components/Sidebar/OllamaTestButton.tsx`**

```tsx
import { checkOllama } from "../../api/client";
import { useStore } from "../../store/store";

export default function OllamaTestButton() {
  const ollama = useStore((s) => s.ollama);
  const setOllama = useStore((s) => s.setOllama);

  const dotClass =
    ollama == null ? "bg-gray-400" : ollama.ok ? "bg-green-500" : "bg-red-500";

  const onTest = async () => {
    try {
      setOllama(await checkOllama());
    } catch (e) {
      setOllama({ ok: false, models: [], error: String(e) });
    }
  };

  return (
    <button
      onClick={onTest}
      title={ollama?.error ?? ollama?.models.join(", ") ?? "미확인"}
      className="flex items-center gap-2 w-full rounded-md px-3 py-2 text-sm hover:bg-paper-dark"
    >
      <span data-testid="ollama-status" className={`h-2.5 w-2.5 rounded-full ${dotClass}`} />
      Ollama 연결 테스트
    </button>
  );
}
```

- [ ] **Step 4: Create `frontend/src/components/Sidebar/SessionList.tsx`**

```tsx
import type { Session } from "../../types";

interface Props {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
}

export default function SessionList({ sessions, activeId, onSelect }: Props) {
  return (
    <ul className="mt-2 flex flex-col gap-1 overflow-y-auto">
      {sessions.map((s) => (
        <li key={s.id}>
          <button
            onClick={() => onSelect(s.id)}
            className={`w-full truncate rounded-md px-3 py-2 text-left text-sm hover:bg-paper-dark ${
              s.id === activeId ? "bg-paper-dark font-medium" : ""
            }`}
          >
            {s.title}
          </button>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 5: Create `frontend/src/components/Sidebar/Sidebar.tsx`**

```tsx
import { useEffect } from "react";
import { createSession, getMessages, listSessions } from "../../api/client";
import { useStore } from "../../store/store";
import OllamaTestButton from "./OllamaTestButton";
import SessionList from "./SessionList";

export default function Sidebar() {
  const sessions = useStore((s) => s.sessions);
  const activeSessionId = useStore((s) => s.activeSessionId);
  const setSessions = useStore((s) => s.setSessions);
  const setActiveSession = useStore((s) => s.setActiveSession);
  const setMessages = useStore((s) => s.setMessages);

  const refresh = async () => setSessions(await listSessions());

  useEffect(() => {
    refresh();
  }, []);

  const onNew = async () => {
    const session = await createSession();
    await refresh();
    setActiveSession(session.id);
    setMessages([]);
  };

  const onSelect = async (id: string) => {
    setActiveSession(id);
    setMessages((await getMessages(id)).messages);
  };

  return (
    <aside className="flex h-full w-64 flex-col border-r border-paper-dark bg-paper p-3">
      <button
        onClick={onNew}
        className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-dark"
      >
        + 새 세션
      </button>
      <div className="mt-2">
        <OllamaTestButton />
      </div>
      <hr className="my-2 border-paper-dark" />
      <SessionList sessions={sessions} activeId={activeSessionId} onSelect={onSelect} />
    </aside>
  );
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && npm test src/components/Sidebar`
Expected: PASS (3 passed)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Sidebar
git commit -m "feat(frontend): add sidebar with sessions and Ollama test"
```

---

### Task 16: Chat panel (mode toggle, thread, composer) + Artifacts + App layout

**Files:**
- Create: `frontend/src/components/Chat/ModeToggle.tsx`
- Create: `frontend/src/components/Chat/MessageList.tsx`
- Create: `frontend/src/components/Chat/Composer.tsx`
- Create: `frontend/src/components/Chat/ChatPanel.tsx`
- Create: `frontend/src/components/Artifacts/ArtifactsPanel.tsx`
- Create: `frontend/src/components/TopBar.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/components/Chat/ChatPanel.test.tsx`
- Test: `frontend/src/components/Artifacts/ArtifactsPanel.test.tsx`

**Interfaces:**
- Consumes: `useStore`, `api/sse.streamChat`, `api/client`.
- Produces:
  - `ModeToggle`: two buttons "Chat"/"PPT"; clicking sets `mode`; active button has `bg-accent text-white`.
  - `MessageList`: renders `messages`; user bubbles right-aligned, assistant left-aligned.
  - `Composer`: textarea + send button; on send (and not `streaming`), appends user message, calls `streamChat` wiring deltas into the store, disables while `streaming`.
  - `ArtifactsPanel`: visible only when `artifactsOpen`; shows placeholder text "Artifacts" with `data-testid="artifacts-panel"`.
  - `TopBar`: hosts `ModeToggle` (left) and an artifacts toggle button (right) calling `toggleArtifacts`.
  - `App`: 3-column layout `Sidebar | (TopBar over ChatPanel) | ArtifactsPanel`.

- [ ] **Step 1: Write the failing test** — `frontend/src/components/Chat/ChatPanel.test.tsx`

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import ChatPanel from "./ChatPanel";
import { useStore } from "../../store/store";
import * as sse from "../../api/sse";

beforeEach(() => {
  useStore.setState({ messages: [], mode: "chat", streaming: false, activeSessionId: "s1" });
});
afterEach(() => vi.restoreAllMocks());

test("sending a message streams assistant deltas into the thread", async () => {
  vi.spyOn(sse, "streamChat").mockImplementation(async (_sid, _content, _mode, h) => {
    h.onToken("Hi ");
    h.onToken("there");
    h.onDone();
  });

  render(<ChatPanel />);
  await userEvent.type(screen.getByRole("textbox"), "hello");
  await userEvent.click(screen.getByRole("button", { name: /전송/ }));

  await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
  await waitFor(() => expect(screen.getByText("Hi there")).toBeInTheDocument());
});

test("mode toggle switches active mode", async () => {
  render(<ChatPanel />);
  await userEvent.click(screen.getByRole("button", { name: "PPT" }));
  expect(useStore.getState().mode).toBe("ppt");
});
```

- [ ] **Step 2: Write the failing test** — `frontend/src/components/Artifacts/ArtifactsPanel.test.tsx`

```tsx
import { render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import ArtifactsPanel from "./ArtifactsPanel";
import { useStore } from "../../store/store";

afterEach(() => useStore.setState({ artifactsOpen: false }));

test("hidden when artifactsOpen is false", () => {
  render(<ArtifactsPanel />);
  expect(screen.queryByTestId("artifacts-panel")).toBeNull();
});

test("visible when artifactsOpen is true", () => {
  useStore.setState({ artifactsOpen: true });
  render(<ArtifactsPanel />);
  expect(screen.getByTestId("artifacts-panel")).toBeInTheDocument();
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npm test src/components/Chat src/components/Artifacts`
Expected: FAIL (cannot resolve modules)

- [ ] **Step 4: Create `frontend/src/components/Chat/ModeToggle.tsx`**

```tsx
import type { Mode } from "../../types";
import { useStore } from "../../store/store";

const MODES: Mode[] = ["chat", "ppt"];

export default function ModeToggle() {
  const mode = useStore((s) => s.mode);
  const setMode = useStore((s) => s.setMode);
  return (
    <div className="flex gap-1 rounded-lg bg-paper-dark p-1">
      {MODES.map((m) => (
        <button
          key={m}
          onClick={() => setMode(m)}
          className={`rounded-md px-3 py-1 text-sm capitalize ${
            mode === m ? "bg-accent text-white" : "text-ink"
          }`}
        >
          {m === "chat" ? "Chat" : "PPT"}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Create `frontend/src/components/Chat/MessageList.tsx`**

```tsx
import type { ChatMessage } from "../../types";

export default function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
      {messages.map((m, i) => (
        <div
          key={i}
          className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-2 text-sm ${
            m.role === "user"
              ? "self-end bg-accent text-white"
              : "self-start bg-white text-ink"
          }`}
        >
          {m.content}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Create `frontend/src/components/Chat/Composer.tsx`**

```tsx
import { useState } from "react";
import { streamChat } from "../../api/sse";
import { useStore } from "../../store/store";

export default function Composer() {
  const [text, setText] = useState("");
  const mode = useStore((s) => s.mode);
  const streaming = useStore((s) => s.streaming);
  const activeSessionId = useStore((s) => s.activeSessionId);
  const appendUserMessage = useStore((s) => s.appendUserMessage);
  const startAssistantMessage = useStore((s) => s.startAssistantMessage);
  const appendAssistantDelta = useStore((s) => s.appendAssistantDelta);
  const setStreaming = useStore((s) => s.setStreaming);

  const onSend = async () => {
    const content = text.trim();
    if (!content || streaming || !activeSessionId) return;
    setText("");
    appendUserMessage(content);
    startAssistantMessage();
    setStreaming(true);
    await streamChat(activeSessionId, content, mode, {
      onToken: (d) => appendAssistantDelta(d),
      onDone: () => setStreaming(false),
      onError: (msg) => {
        appendAssistantDelta(`\n[오류] ${msg}`);
        setStreaming(false);
      },
    });
  };

  return (
    <div className="flex gap-2 border-t border-paper-dark p-3">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSend();
          }
        }}
        rows={2}
        placeholder="메시지를 입력하세요…"
        className="flex-1 resize-none rounded-md border border-paper-dark bg-white p-2 text-sm outline-none"
      />
      <button
        onClick={onSend}
        disabled={streaming}
        className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
      >
        전송
      </button>
    </div>
  );
}
```

- [ ] **Step 7: Create `frontend/src/components/Chat/ChatPanel.tsx`**

```tsx
import ModeToggle from "./ModeToggle";
import MessageList from "./MessageList";
import Composer from "./Composer";
import { useStore } from "../../store/store";

export default function ChatPanel() {
  const messages = useStore((s) => s.messages);
  return (
    <div className="flex h-full flex-1 flex-col">
      <div className="flex items-center justify-between border-b border-paper-dark p-3">
        <ModeToggle />
      </div>
      <MessageList messages={messages} />
      <Composer />
    </div>
  );
}
```

- [ ] **Step 8: Create `frontend/src/components/Artifacts/ArtifactsPanel.tsx`**

```tsx
import { useStore } from "../../store/store";

export default function ArtifactsPanel() {
  const artifactsOpen = useStore((s) => s.artifactsOpen);
  if (!artifactsOpen) return null;
  return (
    <aside
      data-testid="artifacts-panel"
      className="flex h-full w-80 flex-col border-l border-paper-dark bg-paper p-4"
    >
      <h2 className="text-sm font-semibold text-ink">Artifacts</h2>
      <p className="mt-4 text-sm text-ink/60">
        아직 표시할 artifact가 없습니다. PPT 기능이 추가되면 여기에 미리보기가 나타납니다.
      </p>
    </aside>
  );
}
```

- [ ] **Step 9: Create `frontend/src/components/TopBar.tsx`**

```tsx
import { useStore } from "../store/store";

export default function TopBar() {
  const toggleArtifacts = useStore((s) => s.toggleArtifacts);
  const artifactsOpen = useStore((s) => s.artifactsOpen);
  return (
    <div className="flex items-center justify-end border-b border-paper-dark bg-paper px-4 py-2">
      <button
        onClick={toggleArtifacts}
        className={`rounded-md border border-paper-dark px-3 py-1 text-sm ${
          artifactsOpen ? "bg-accent text-white" : "text-ink"
        }`}
      >
        Artifacts {artifactsOpen ? "▣" : "▢"}
      </button>
    </div>
  );
}
```

- [ ] **Step 10: Replace `frontend/src/App.tsx`**

```tsx
import Sidebar from "./components/Sidebar/Sidebar";
import TopBar from "./components/TopBar";
import ChatPanel from "./components/Chat/ChatPanel";
import ArtifactsPanel from "./components/Artifacts/ArtifactsPanel";

export default function App() {
  return (
    <div className="flex h-screen bg-paper text-ink">
      <Sidebar />
      <main className="flex flex-1 flex-col">
        <TopBar />
        <ChatPanel />
      </main>
      <ArtifactsPanel />
    </div>
  );
}
```

> NOTE: `App.test.tsx` from Task 12 asserted `bg-paper` on the root `div`, which still holds. But `App` now mounts `Sidebar`, whose `useEffect` calls `listSessions()`. Update the test to stub it so no unmocked `fetch` runs.

- [ ] **Step 11: Update `frontend/src/App.test.tsx`** to stub the sidebar's session load

```tsx
import { render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";
import * as client from "./api/client";

afterEach(() => vi.restoreAllMocks());

test("renders app shell with paper background", () => {
  vi.spyOn(client, "listSessions").mockResolvedValue([]);
  const { container } = render(<App />);
  const root = container.firstChild as HTMLElement;
  expect(root.className).toContain("bg-paper");
});
```

- [ ] **Step 12: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS (all component + store + api tests green)

- [ ] **Step 13: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): add chat panel, artifacts panel, and app layout"
```

---

## Manual Verification (after all tasks)

These require a real Ollama (`ollama pull gemma3n:e4b`, `ollama serve`):

- [ ] Backend: `cd backend && uvicorn app.main:app --reload` → open `http://localhost:8000/docs`.
- [ ] Frontend: `cd frontend && npm run dev` → open `http://localhost:5173`.
- [ ] Click "Ollama 연결 테스트" → green dot, model list in tooltip.
- [ ] "+ 새 세션" → type a message in Chat mode → tokens stream in; session auto-titles.
- [ ] Switch to PPT mode → send → "준비 중" stub streams back.
- [ ] Toggle Artifacts panel on/off.
- [ ] Restart backend → reopen session → history persists.

## Spec Coverage Map

| Spec requirement | Task |
|---|---|
| Ollama 연결 테스트 버튼 (좌측) | 9 (API), 15 (UI) |
| 세션별 기록 + 세션 추가 버튼 (좌측 상단) | 7, 10 (API), 15 (UI) |
| 베이지+주황 테마 | 12 |
| artifacts on/off (상단) | 16 |
| Gemma-e4b, env api_key 슬롯 | 1, 2 |
| LangGraph PPT agent (subgraph 자리) | 5 |
| chat/ppt 모드 토글 → master 라우팅 | 3, 6 (graph), 16 (UI) |
| chat 노드 기본 채팅 | 4, 11 |
| SSE 스트리밍 | 11, 13 |
| SQLite 영속화 | 7, 8 |
