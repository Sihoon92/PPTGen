# PPT 파이프라인 트레이싱 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PPT 파이프라인의 모든 LLM 호출(프롬프트+raw 응답)과 렌더 단계 입력/에러(스택 포함)를 run 단위 JSON으로 기록해 렌더 에러 원인을 진단 가능하게 한다.

**Architecture:** 요청마다 `TracingCallbackHandler`를 그래프 `config["callbacks"]`에 붙여 모든 LLM 호출을 자동 캡처하고(LangChain이 run 상관관계·`metadata.langgraph_node` 제공), 렌더는 subprocess이므로 렌더러를 명시 계측한다. 기존 `TraceWriter`를 run의 단일 소유자로 두고 노드 이벤트 + LLM 호출 + 렌더 레코드를 한 파일에 병합한다.

**Tech Stack:** Python 3.11+, FastAPI, LangGraph, LangChain(`langchain-core` 콜백), pytest + pytest-asyncio(`asyncio_mode=auto`), Node + PptxGenJS sidecar.

## Global Constraints

- 트레이싱은 **절대 사용자 응답/파이프라인을 깨지 않는다**: 콜백·job 덤프·flush는 모두 `try/except`로 감싸 실패해도 무시. (기존 `flush()`의 `except: pass` 패턴 준수.)
- `PptState`는 **JSON 직렬화 가능**해야 한다(SQLite 체크포인터). 레코더 객체를 상태에 싣지 않는다. 추가 상태 키는 dict/list 등 직렬화 가능 값만.
- 영속 파일의 노드 배열 키는 기존 **`events`** 를 유지(프론트 호환). 개별 노드 이벤트 dict의 필드 형태(`node/label/kind/tool/step/ts/status/summary/output/error`)는 변경 금지 — SSE `node` 이벤트가 동일 dict를 사용.
- `prompt`/`raw_response`는 truncation 안 함. 단 호출당 상한 `MAX_FIELD = 256 * 1024` 초과 시에만 말줄임.
- 테스트는 `backend/` 디렉터리에서 실행: `python -m pytest ...`. async 테스트는 마커 불필요(`asyncio_mode=auto`).
- 커밋 트레일러(레포 관례):
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_016pNBQ8ccuYB5tQmvALV26k
  ```

---

## File Structure

| 파일 | 책임 | 작업 |
|---|---|---|
| `backend/app/ppt/renderer.py` | 렌더 결과 파싱(스택/stderr 보존, 무절단) + job 덤프 | 수정 (Task 1) |
| `backend/app/ppt/trace.py` | `TraceWriter` 스키마 확장 + render status 교정 + `TracingCallbackHandler` + `label_config` | 수정 (Task 2, 3) |
| `backend/app/graph/state.py` | `PptState`에 `render_report` 키 추가 | 수정 (Task 4) |
| `backend/app/graph/nodes/ppt_nodes/stages.py` | dsl 노드 config 수신·라벨, render_node render_report | 수정 (Task 4) |
| `backend/app/graph/nodes/ppt_nodes/supervisor.py` | `_classify_intent` config·라벨 | 수정 (Task 4) |
| `backend/app/api/chat.py` | cfg에 callbacks + trace_run_id 주입 | 수정 (Task 4) |
| `backend/tests/test_renderer.py` | 렌더 파싱/덤프 테스트 | 생성 (Task 1) |
| `backend/tests/test_trace.py` | TraceWriter 스키마/status 테스트 | 생성 (Task 2) |
| `backend/tests/test_trace_callback.py` | 콜백 핸들러 테스트 | 생성 (Task 3) |
| `backend/tests/test_render_node.py` | render_node render_report 테스트 | 생성 (Task 4) |
| `backend/tests/test_trace_integration.py` | 병합 스키마 계약 테스트 | 생성 (Task 5) |

`render.mjs`는 변경 없음 — 이미 `{ok:false, error, stack}`을 반환한다(`render.mjs:95-99`).

---

## Task 1: 렌더러 — 전체 에러/스택/stderr 보존 + job 덤프

**Files:**
- Modify: `backend/app/ppt/renderer.py`
- Test: `backend/tests/test_renderer.py` (create)

**Interfaces:**
- Produces:
  - `RenderResult(ok: bool, out_path: str|None, slide_count: int, error: str|None, stack: str|None, stderr: str|None)`
  - `_parse_render_result(stdout: bytes, stderr: bytes, returncode: int, out_path: str) -> RenderResult`
  - `render_deck(layout_irs, theme, out_path, node_bin="node", job_dump_path: str|None=None) -> RenderResult`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_renderer.py`:

```python
import json

import pytest

from app.ppt.renderer import _parse_render_result, render_deck


def test_parse_preserves_stack_and_stderr():
    stdout = json.dumps(
        {"ok": False, "error": "boom", "stack": "Error: boom\n  at main"}
    ).encode("utf-8")
    r = _parse_render_result(stdout, b"warn on stderr", 1, "/x/out.pptx")
    assert r.ok is False
    assert r.error == "boom"
    assert r.stack == "Error: boom\n  at main"
    assert r.stderr == "warn on stderr"


def test_parse_does_not_truncate_error():
    big = "x" * 5000
    stdout = json.dumps({"ok": False, "error": big}).encode("utf-8")
    r = _parse_render_result(stdout, b"", 1, "/x/out.pptx")
    assert len(r.error) == 5000  # previously truncated to 500


def test_parse_success():
    stdout = json.dumps(
        {"ok": True, "out_path": "/x/out.pptx", "slide_count": 3}
    ).encode("utf-8")
    r = _parse_render_result(stdout, b"", 0, "/x/out.pptx")
    assert r.ok is True
    assert r.slide_count == 3


def test_parse_non_json_stdout_falls_back_to_stderr():
    r = _parse_render_result(b"not json", b"real error text", 1, "/x/out.pptx")
    assert r.ok is False
    assert "real error text" in r.error


async def test_render_deck_dumps_job_before_spawn(tmp_path):
    job_path = tmp_path / "render_job_test.json"
    out_path = tmp_path / "out.pptx"
    r = await render_deck(
        [{"slide_id": "s1", "elements": []}],
        {"colors": {"background": "FFFFFF"}},
        str(out_path),
        node_bin="definitely-not-a-real-binary-xyz",
        job_dump_path=str(job_path),
    )
    assert job_path.exists()  # written even though the binary is missing
    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["slides"][0]["slide_id"] == "s1"
    assert r.ok is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_renderer.py -v`
Expected: FAIL — `ImportError: cannot import name '_parse_render_result'` (and `RenderResult` has no `stack`).

- [ ] **Step 3: Rewrite `renderer.py`**

Replace the body of `backend/app/ppt/renderer.py` from the `@dataclass` line through the end of `render_deck` with:

```python
@dataclass
class RenderResult:
    ok: bool
    out_path: str | None = None
    slide_count: int = 0
    error: str | None = None
    stack: str | None = None
    stderr: str | None = None


def _parse_render_result(
    stdout: bytes, stderr: bytes, returncode: int, out_path: str
) -> RenderResult:
    """Parse the sidecar's stdout/stderr into a RenderResult.

    Preserves the full JS error message, stack, and stderr (no truncation) so a
    PptxGenJS failure can be diagnosed offline.
    """
    stderr_text = stderr.decode("utf-8", "replace").strip()
    try:
        result = json.loads(stdout.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return RenderResult(
            ok=False,
            error=stderr_text or "renderer produced no JSON output",
            stderr=stderr_text or None,
        )
    if returncode != 0 or not result.get("ok"):
        return RenderResult(
            ok=False,
            error=str(result.get("error") or stderr_text or "render failed"),
            stack=result.get("stack"),
            stderr=stderr_text or None,
        )
    return RenderResult(
        ok=True,
        out_path=result.get("out_path", out_path),
        slide_count=int(result.get("slide_count", 0)),
    )


async def render_deck(
    layout_irs: list[dict[str, Any]],
    theme: dict[str, Any],
    out_path: str,
    node_bin: str = "node",
    job_dump_path: str | None = None,
) -> RenderResult:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    job = json.dumps({"out_path": out_path, "theme": theme, "slides": layout_irs})

    # Persist the exact render input BEFORE spawning so even a crash/hang leaves a
    # reproducible job (`node render.mjs < render_job_*.json`). Best-effort only.
    if job_dump_path:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(job_dump_path)), exist_ok=True)
            with open(job_dump_path, "w", encoding="utf-8") as fh:
                fh.write(job)
        except Exception:  # noqa: BLE001 - tracing must never break render
            pass

    try:
        proc = await asyncio.create_subprocess_exec(
            node_bin,
            str(SCRIPT_PATH),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return RenderResult(ok=False, error=f"node binary not found: {node_bin!r}")

    stdout, stderr = await proc.communicate(job.encode("utf-8"))
    result = _parse_render_result(stdout, stderr, proc.returncode, out_path)
    if result.ok and not result.slide_count:
        result.slide_count = len(layout_irs)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_renderer.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/ppt/renderer.py backend/tests/test_renderer.py
git commit -m "feat(trace): preserve full render error/stack/stderr + dump render job

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016pNBQ8ccuYB5tQmvALV26k"
```

---

## Task 2: TraceWriter — 스키마 확장 + render status 교정 + label_config

**Files:**
- Modify: `backend/app/ppt/trace.py`
- Test: `backend/tests/test_trace.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `TraceWriter.llm_calls: list[dict]`, `TraceWriter.render: dict | None`
  - `TraceWriter.add_llm_call(record: dict) -> None`
  - `label_config(config: dict | None, label: str) -> dict` (merges `metadata.trace_label`)
  - flushed file gains top-level `backend`, `model`, `ok`, `ended_at`, `llm_calls`, `render`; node array stays under key `events`.
  - render node event `status == "error"` when output has no `artifact`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_trace.py`:

```python
import json

from app.ppt.trace import TraceWriter, label_config


def _result_event(name, result):
    return {
        "type": "task_result",
        "step": 1,
        "timestamp": "t",
        "payload": {"name": name, "result": result},
    }


def test_label_config_merges_metadata_without_mutating():
    cfg = {"configurable": {"thread_id": "s1"}, "metadata": {"a": 1}}
    out = label_config(cfg, "deck_spec")
    assert out["metadata"]["trace_label"] == "deck_spec"
    assert out["metadata"]["a"] == 1
    assert out["configurable"]["thread_id"] == "s1"
    assert "trace_label" not in (cfg["metadata"])  # original untouched


def test_label_config_handles_none():
    out = label_config(None, "intent_classify")
    assert out["metadata"]["trace_label"] == "intent_classify"


def test_render_failure_marks_status_error_and_captures_report():
    w = TraceWriter("s1", "title")
    report = {"attempted": True, "ok": False, "error": "boom", "stack": "S"}
    ev = w.handle(
        ("ppt",),
        _result_event("render", {"issues": [{"code": "render_failed"}], "render_report": report}),
    )
    assert ev["status"] == "error"
    assert w.render == report


def test_render_success_keeps_done_status():
    w = TraceWriter("s1", "title")
    ev = w.handle(
        ("ppt",),
        _result_event("render", {"artifact": {"slide_count": 2}, "output_path": "/x.pptx"}),
    )
    assert ev["status"] == "done"


async def test_flush_writes_extended_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path))
    w = TraceWriter("s1", "deck title")
    w.add_llm_call({"seq": 1, "label": "deck_spec", "prompt": "p", "raw_response": "r"})
    w.handle(("ppt",), _result_event("render", {"render_report": {"attempted": True, "ok": False}}))
    w.flush()

    data = json.loads((tmp_path / "s1" / "trace_latest.json").read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert data["backend"]  # non-empty (default "ollama")
    assert data["model"]
    assert len(data["llm_calls"]) == 1
    assert data["render"] == {"attempted": True, "ok": False}
    assert "events" in data  # node array key preserved for the frontend
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_trace.py -v`
Expected: FAIL — `ImportError: cannot import name 'label_config'`.

- [ ] **Step 3: Edit `trace.py`**

3a. Add the import for settings is already present. Add `label_config` near the top, after the `NODE_META` block:

```python
def label_config(config: dict | None, label: str) -> dict:
    """Return a copy of ``config`` with ``metadata.trace_label`` set.

    Used by LLM-calling nodes so the callback handler can name each call
    (e.g. ``deck_spec`` vs ``slide_planner``) without mutating the caller's config.
    """
    config = config or {}
    metadata = {**(config.get("metadata") or {}), "trace_label": label}
    return {**config, "metadata": metadata}
```

3b. In `TraceWriter.__init__`, add two accumulators (after `self.events: list[dict] = []`):

```python
        self.llm_calls: list[dict] = []
        self.render: dict | None = None
```

3c. Add the `add_llm_call` method (after `__init__`):

```python
    def add_llm_call(self, record: dict) -> None:
        """Append one LLM-call record (from TracingCallbackHandler)."""
        self.llm_calls.append(record)
```

3d. In `handle()`, inside the `else:` branch (task_result), AFTER the existing
`event["output"] = _safe(out)` and the `if error:` block, add render-specific handling:

```python
            if name == "render":
                report = out.get("render_report")
                if isinstance(report, dict):
                    self.render = report
                # render_node never raises; it returns an apology + issues. Mark the
                # event as an error when no artifact was produced so the trace reflects it.
                if not error and not out.get("artifact"):
                    event["status"] = "error"
```

3e. Replace the `flush()` body's `payload = {...}` dict with the extended schema and
record `ended_at`:

```python
    def flush(self) -> None:
        if not self.events:
            return
        try:
            settings = get_settings()
            base = Path(settings.artifacts_dir) / self.session_id
            base.mkdir(parents=True, exist_ok=True)
            payload = {
                "session_id": self.session_id,
                "run_id": self.run_id,
                "title": self.title,
                "started_at": self.started_at.isoformat(timespec="seconds"),
                "ended_at": datetime.now().isoformat(timespec="seconds"),
                "backend": settings.llm_backend,
                "model": settings.active_model,
                "ok": self._ok(),
                "events": self.events,
                "llm_calls": self.llm_calls,
                "render": self.render,
            }
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            (base / f"trace_{self.run_id}.json").write_text(text, encoding="utf-8")
            (base / "trace_latest.json").write_text(text, encoding="utf-8")

            traces = Path(settings.artifacts_dir) / "traces"
            traces.mkdir(parents=True, exist_ok=True)
            fname = (
                f"{self.started_at:%Y%m%d-%H%M%S}"
                f"_{_slugify(self.title)}_{self.run_id[:6]}.json"
            )
            (traces / fname).write_text(text, encoding="utf-8")
            (traces / "latest.json").write_text(text, encoding="utf-8")
        except Exception:  # noqa: BLE001 - tracing must never break the response
            pass
```

3f. Add the `_ok` helper method to `TraceWriter`:

```python
    def _ok(self) -> bool:
        """Whole-run success: no error node events, and render (if attempted) succeeded."""
        if any(e.get("status") == "error" for e in self.events):
            return False
        if self.render is not None:
            return bool(self.render.get("ok"))
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_trace.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/ppt/trace.py backend/tests/test_trace.py
git commit -m "feat(trace): extend TraceWriter schema (llm_calls/render/ok) + render status fix

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016pNBQ8ccuYB5tQmvALV26k"
```

---

## Task 3: TracingCallbackHandler — LLM 호출 자동 캡처

**Files:**
- Modify: `backend/app/ppt/trace.py`
- Test: `backend/tests/test_trace_callback.py` (create)

**Interfaces:**
- Consumes: `TraceWriter.add_llm_call` (Task 2).
- Produces: `TracingCallbackHandler(writer: TraceWriter)` with async methods
  `on_chat_model_start`, `on_llm_end`, `on_llm_error`. Each finalized record has:
  `seq, node, label, model, started_at, ended_at, latency_ms, prompt, raw_response,
  token_usage, status, error`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trace_callback.py`:

```python
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from app.ppt.trace import TraceWriter, TracingCallbackHandler


async def test_handler_records_prompt_and_raw():
    w = TraceWriter("s1", "title")
    h = TracingCallbackHandler(w)
    await h.on_chat_model_start(
        {"name": "ChatOllama"},
        [[HumanMessage(content="hello prompt")]],
        run_id="run-1",
        metadata={"langgraph_node": "dsl", "trace_label": "deck_spec"},
    )
    gen = SimpleNamespace(text="raw output", message=None)
    response = SimpleNamespace(generations=[[gen]], llm_output={"token_usage": {"output": 5}})
    await h.on_llm_end(response, run_id="run-1")

    assert len(w.llm_calls) == 1
    rec = w.llm_calls[0]
    assert rec["seq"] == 1
    assert rec["node"] == "dsl"
    assert rec["label"] == "deck_spec"
    assert "hello prompt" in rec["prompt"]
    assert rec["raw_response"] == "raw output"
    assert rec["status"] == "ok"
    assert rec["token_usage"] == {"output": 5}


async def test_handler_records_error():
    w = TraceWriter("s1", "title")
    h = TracingCallbackHandler(w)
    await h.on_chat_model_start(
        {"name": "ChatOllama"},
        [[HumanMessage(content="p")]],
        run_id="run-2",
        metadata={"langgraph_node": "dsl", "trace_label": "slide_planner"},
    )
    await h.on_llm_error(RuntimeError("model exploded"), run_id="run-2")

    assert len(w.llm_calls) == 1
    rec = w.llm_calls[0]
    assert rec["status"] == "error"
    assert "model exploded" in rec["error"]


async def test_handler_ignores_unmatched_end():
    w = TraceWriter("s1", "title")
    h = TracingCallbackHandler(w)
    # on_llm_end with no prior start must not raise and must not append.
    await h.on_llm_end(SimpleNamespace(generations=[[]], llm_output={}), run_id="ghost")
    assert w.llm_calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_trace_callback.py -v`
Expected: FAIL — `ImportError: cannot import name 'TracingCallbackHandler'`.

- [ ] **Step 3: Add the handler + helpers to `trace.py`**

3a. Add imports at the top of `trace.py` (with the existing imports):

```python
import time
from langchain_core.callbacks import AsyncCallbackHandler
```

3b. Add module-level helpers near `_safe` (the `MAX_FIELD` cap and extractors):

```python
MAX_FIELD = 256 * 1024  # per-field cap for prompt/raw_response (rarely hit locally)


def _cap(text: str | None) -> str:
    text = text or ""
    return text if len(text) <= MAX_FIELD else text[:MAX_FIELD] + "…[truncated]"


def _messages_to_text(messages: Any) -> str:
    """Flatten on_chat_model_start's list[list[BaseMessage]] into prompt text."""
    parts: list[str] = []
    for batch in messages or []:
        for m in batch or []:
            parts.append(m if isinstance(m, str) else str(getattr(m, "content", "")))
    return "\n".join(parts)


def _llm_result_text(response: Any) -> str:
    try:
        gen = response.generations[0][0]
        text = getattr(gen, "text", "") or ""
        if text:
            return text
        msg = getattr(gen, "message", None)
        return str(getattr(msg, "content", "")) if msg is not None else ""
    except Exception:  # noqa: BLE001
        return ""


def _usage(response: Any) -> dict | None:
    try:
        out = response.llm_output or {}
        return out.get("token_usage") or out.get("usage") or None
    except Exception:  # noqa: BLE001
        return None
```

3c. Add the handler class at the end of `trace.py`:

```python
class TracingCallbackHandler(AsyncCallbackHandler):
    """Captures every LLM call (prompt + raw response) into a TraceWriter.

    Attached per request via ``config["callbacks"]``. LangChain delivers the node
    name as ``metadata["langgraph_node"]``; nodes add ``metadata["trace_label"]``
    (via ``label_config``) to name each call. Callback exceptions are swallowed by
    LangChain's callback manager, so a failure here never breaks the run.
    """

    def __init__(self, writer: TraceWriter) -> None:
        self.writer = writer
        self._pending: dict[Any, dict] = {}  # run_id -> partial record
        self._seq = 0

    async def on_chat_model_start(
        self, serialized, messages, *, run_id, metadata=None, **kwargs
    ) -> None:
        meta = metadata or {}
        self._pending[run_id] = {
            "node": meta.get("langgraph_node"),
            "label": meta.get("trace_label"),
            "model": (serialized or {}).get("name") or get_settings().active_model,
            "prompt": _cap(_messages_to_text(messages)),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "_start": time.monotonic(),
        }

    async def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        rec = self._pending.pop(run_id, None)
        if rec is not None:
            self._finalize(rec, _llm_result_text(response), _usage(response), "ok", None)

    async def on_llm_error(self, error, *, run_id, **kwargs) -> None:
        rec = self._pending.pop(run_id, None)
        if rec is not None:
            self._finalize(rec, "", None, "error", str(error))

    def _finalize(self, rec, raw, token_usage, status, error) -> None:
        self._seq += 1
        start = rec.pop("_start", None)
        rec["seq"] = self._seq
        rec["ended_at"] = datetime.now().isoformat(timespec="seconds")
        rec["latency_ms"] = int((time.monotonic() - start) * 1000) if start else None
        rec["raw_response"] = _cap(raw)
        rec["token_usage"] = token_usage
        rec["status"] = status
        rec["error"] = error
        self.writer.add_llm_call(rec)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_trace_callback.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/ppt/trace.py backend/tests/test_trace_callback.py
git commit -m "feat(trace): add TracingCallbackHandler to capture LLM prompt/response

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016pNBQ8ccuYB5tQmvALV26k"
```

---

## Task 4: 배선 — config 전파, 라벨, render_report

**Files:**
- Modify: `backend/app/graph/state.py`
- Modify: `backend/app/graph/nodes/ppt_nodes/stages.py`
- Modify: `backend/app/graph/nodes/ppt_nodes/supervisor.py`
- Modify: `backend/app/api/chat.py`
- Test: `backend/tests/test_render_node.py` (create)

**Interfaces:**
- Consumes: `label_config` (Task 2), `render_deck(..., job_dump_path=)` (Task 1),
  `TracingCallbackHandler` (Task 3).
- Produces:
  - `PptState` gains `render_report: dict`.
  - `render_node(state, config)` returns `render_report` in its state delta.
  - `dsl(state, config)` and `supervisor(state, config)` pass `label_config(config, ...)`
    to `model.ainvoke`.
  - `stream_graph` injects `cfg["callbacks"]=[handler]` and
    `cfg["configurable"]["trace_run_id"]=tracer.run_id`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_render_node.py`:

```python
from app.graph.nodes.ppt_nodes.stages import render_node


async def test_render_node_reports_failure_and_dumps_job(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("NODE_BIN", "definitely-not-a-real-binary-xyz")
    state = {
        "session_id": "s1",
        "layout_irs": [{"slide_id": "s1", "elements": []}],
        "theme": {"colors": {"background": "FFFFFF"}},
    }
    config = {"configurable": {"trace_run_id": "run-xyz"}}

    out = await render_node(state, config)

    report = out["render_report"]
    assert report["attempted"] is True
    assert report["ok"] is False
    assert report["job_file"] == "render_job_run-xyz.json"
    assert (tmp_path / "s1" / "render_job_run-xyz.json").exists()
    # pipeline still degrades gracefully
    assert out["messages"]


async def test_render_node_no_slides_reports_not_attempted(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path))
    out = await render_node({"session_id": "s1", "layout_irs": []}, {"configurable": {}})
    assert out["render_report"]["attempted"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_render_node.py -v`
Expected: FAIL — `TypeError: render_node() takes 1 positional argument but 2 were given`.

- [ ] **Step 3a: Add `render_report` to `PptState`**

In `backend/app/graph/state.py`, inside `PptState`, add to the "pipeline artifacts" group
(after `output_path: str`):

```python
    render_report: dict  # render diagnostics (ok/job_file/error/stack/stderr) for the trace
```

- [ ] **Step 3b: Update `stages.py`**

3b-i. Update imports at the top of `stages.py`:

```python
from app.ppt.trace import label_config
```

3b-ii. Change the `dsl` node signature and both `ainvoke` calls. Replace
`async def dsl(state: PptState) -> dict:` with `async def dsl(state: PptState, config: dict) -> dict:`,
then the two model calls:

```python
        resp = await model.ainvoke(
            [HumanMessage(content=DECK_SPEC_PROMPT.format(brief=brief))],
            label_config(config, "deck_spec"),
        )
```

```python
        resp = await model.ainvoke(
            [HumanMessage(content=prompt)], label_config(config, "slide_planner")
        )
```

3b-iii. Replace the entire `render_node` function with:

```python
async def render_node(state: PptState, config: dict) -> dict:
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
        return {
            "issues": issues,
            "messages": [AIMessage(content=_FAIL_MSG)],
            "render_report": {"attempted": False, "ok": False, "error": "no slides"},
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
        issues = list(state.get("issues", []) or [])
        issues.append(Issue(stage="render", code="render_failed",
                            message=result.error or "render failed").model_dump())
        return {
            "issues": issues,
            "messages": [AIMessage(content=_FAIL_MSG)],
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
```

- [ ] **Step 3c: Update `supervisor.py`**

3c-i. Add import:

```python
from app.ppt.trace import label_config
```

3c-ii. Change `_classify_intent` to accept and pass config:

```python
async def _classify_intent(model: BaseChatModel, request: str, config: dict) -> str:
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
```

3c-iii. Change the supervisor node signature and the `_classify_intent` call site.
Replace `async def supervisor(state: PptState) -> dict:` with
`async def supervisor(state: PptState, config: dict) -> dict:`, and the call
`start = await _classify_intent(model, _last_human(state))` with:

```python
                start = await _classify_intent(model, _last_human(state), config)
```

- [ ] **Step 3d: Update `chat.py`**

In `stream_graph`, replace the line `tracer = TraceWriter(session_id, title)` with the
handler setup + cfg injection:

```python
    tracer = TraceWriter(session_id, title)
    handler = TracingCallbackHandler(tracer)
    cfg = {
        **cfg,
        "callbacks": [handler],
        "configurable": {**(cfg.get("configurable") or {}), "trace_run_id": tracer.run_id},
    }
```

And update the import line:

```python
from app.ppt.trace import TraceWriter, TracingCallbackHandler
```

- [ ] **Step 4: Run the full test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: PASS — new `test_render_node.py` passes (2) and no regressions in existing tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/state.py backend/app/graph/nodes/ppt_nodes/stages.py backend/app/graph/nodes/ppt_nodes/supervisor.py backend/app/api/chat.py backend/tests/test_render_node.py
git commit -m "feat(trace): wire callback handler + config labels + render_report

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016pNBQ8ccuYB5tQmvALV26k"
```

---

## Task 5: 병합 스키마 계약 테스트 (integration)

**Files:**
- Test: `backend/tests/test_trace_integration.py` (create)

**Interfaces:**
- Consumes: `TraceWriter`, `TracingCallbackHandler` (Tasks 2–3).

이 테스트는 그래프 전체를 띄우지 않고, 콜백 핸들러 + TraceWriter + flush가 함께 동작했을 때
디스크 파일이 설계 스키마(섹션 5)대로 나오는지 계약(contract)을 검증한다. 실제 그래프 end-to-end
재현은 수동 검증(아래 "Manual verification")으로 갈음한다.

- [ ] **Step 1: Write the test**

Create `backend/tests/test_trace_integration.py`:

```python
import json
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from app.ppt.trace import TraceWriter, TracingCallbackHandler


def _result_event(name, result):
    return {
        "type": "task_result",
        "step": 1,
        "timestamp": "t",
        "payload": {"name": name, "result": result},
    }


async def test_merged_trace_file_matches_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path))
    w = TraceWriter("s1", "deck title")
    h = TracingCallbackHandler(w)

    # Two LLM calls from the dsl node (deck_spec + slide_planner).
    for i, label in enumerate(["deck_spec", "slide_planner"]):
        rid = f"run-{i}"
        await h.on_chat_model_start(
            {"name": "ChatOllama"},
            [[HumanMessage(content=f"prompt {i}")]],
            run_id=rid,
            metadata={"langgraph_node": "dsl", "trace_label": label},
        )
        gen = SimpleNamespace(text=f"raw {i}", message=None)
        await h.on_llm_end(SimpleNamespace(generations=[[gen]], llm_output={}), run_id=rid)

    # Node events incl. a render failure carrying a render_report.
    w.handle(("ppt",), _result_event("dsl", {"deck_spec": {"title": "t"}, "slide_dsls": [{}]}))
    w.handle(
        ("ppt",),
        _result_event(
            "render",
            {"render_report": {"attempted": True, "ok": False, "error": "boom", "stack": "S"}},
        ),
    )
    w.flush()

    data = json.loads((tmp_path / "s1" / "trace_latest.json").read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert data["backend"] and data["model"]
    assert [c["label"] for c in data["llm_calls"]] == ["deck_spec", "slide_planner"]
    assert data["llm_calls"][0]["prompt"].endswith("prompt 0")
    assert data["llm_calls"][1]["raw_response"] == "raw 1"
    assert data["render"]["stack"] == "S"
    # render node event was promoted to error
    render_ev = [e for e in data["events"] if e["node"] == "render"][0]
    assert render_ev["status"] == "error"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_trace_integration.py -v`
Expected: PASS (1 passed). (All code under test already exists after Tasks 2–3.)

- [ ] **Step 3: Run the full suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: PASS — all tests green.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_trace_integration.py
git commit -m "test(trace): contract test for merged run trace schema

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016pNBQ8ccuYB5tQmvALV26k"
```

---

## Manual Verification (the actual bug)

계획 구현 후, 실제 렌더 에러를 진단한다:

1. 백엔드 실행 후 PPT 생성을 한 번 트리거(에러 재현).
2. `artifacts/<session>/trace_latest.json` 열기 → `render.error` / `render.stack` / `render.stderr`
   확인(이제 잘리지 않고 JS 스택 포함).
3. `artifacts/<session>/render_job_<run>.json`로 단독 재현:
   ```bash
   cd backend/app/ppt/node_renderer
   node render.mjs < ../../../../artifacts/<session>/render_job_<run>.json
   ```
   stdout의 `{ok:false, error, stack}`로 PptxGenJS 실패 지점을 특정한다.
4. `llm_calls`에서 `slide_planner`의 `raw_response`가 유효한 레이아웃을 만들었는지 교차 확인
   (잘못된 IR이 렌더 실패를 유발했는지 판단).

---

## Self-Review

- **Spec coverage**: LLM 호출 1회=1레코드(Task 3), 프롬프트+raw(Task 3), 렌더 job 저장(Task 1),
  전체 에러+스택+stderr(Task 1), status=error 교정(Task 2), 디스크 JSON(Task 2 flush),
  backend/model/ok 최상위(Task 2) — 모두 태스크에 매핑됨. ✅
- **Placeholder scan**: 모든 코드 step에 실제 코드 포함, TBD/TODO 없음. ✅
- **Type consistency**: `RenderResult.stack/stderr`(T1) → render_node가 읽음(T4); `add_llm_call`(T2)
  → handler가 호출(T3); `label_config`(T2) → stages/supervisor가 사용(T4); `render_report` 키(T4)
  → TraceWriter.handle이 읽음(T2). 명칭 일관. ✅
- **Deviation note**: 파일의 노드 배열 키는 스펙의 `nodes` 대신 기존 `events` 유지(프론트 호환). 의도적.
- **Deviation note (구현 중 정정)**: 노드 시그니처는 `config: dict`가 아니라 **`config: RunnableConfig`**(render_node/supervisor는 `= None` 기본값)로 작성해야 한다. LangGraph는 노드 콜러블의 두 번째 인자가 `RunnableConfig`로 **어노테이트된 경우에만** config(callbacks·configurable)를 주입한다. `dict`로 두면 callbacks/`trace_run_id`가 노드에 도달하지 않아 기능이 조용히 무력화된다(빈 `llm_calls`). Task 4에서 이 정정을 적용했고 그래프 레벨 배선 테스트로 가드한다.
