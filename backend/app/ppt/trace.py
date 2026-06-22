"""Execution tracing for the PPT subgraph.

Turns LangGraph's ``debug`` stream (task / task_result events) into compact,
JSON-safe trace records — one per node start and completion — so the UI can show
which node is running, which tool it used, and what it produced. Records are also
persisted per run to ``<artifacts_dir>/<session>/trace_<run>.json`` for offline
debugging.

Only nodes inside the ``ppt`` subgraph are traced (namespace starts with ``ppt``);
top-level routing nodes are ignored to keep the trace focused.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.callbacks import AsyncCallbackHandler

from app.config import get_settings

# node name -> (kind, human label). kind drives the "tool" shown in the UI.
NODE_META: dict[str, tuple[str, str]] = {
    "supervisor": ("router", "라우팅 결정"),
    "dsl": ("llm", "슬라이드 DSL 생성"),
    "compiler": ("code", "레이아웃 컴파일"),
    "render": ("render", "PPTX 렌더"),
}


def label_config(config: dict | None, label: str) -> dict:
    """Return a copy of ``config`` with ``metadata.trace_label`` set.

    Used by LLM-calling nodes so the callback handler can name each call
    (e.g. ``deck_spec`` vs ``slide_planner``) without mutating the caller's config.
    """
    config = config or {}
    metadata = {**(config.get("metadata") or {}), "trace_label": label}
    return {**config, "metadata": metadata}


def _slugify(title: str | None) -> str:
    """Turn a session title into a filesystem-safe filename fragment.

    Keeps Korean/unicode letters (NTFS supports them); strips the ``…`` ellipsis
    that ``_derive_title`` appends, path-unsafe chars, and control chars; collapses
    whitespace to ``_``; truncates. Falls back to ``"untitled"`` when empty.
    """
    text = (title or "").replace("…", "").strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text)
    text = re.sub(r"\s+", "_", text)
    text = text.strip("_")[:30]
    return text or "untitled"


def _tool_for(kind: str) -> str | None:
    if kind == "llm":
        return get_settings().active_model
    if kind == "render":
        return "Node/PptxGenJS"
    if kind == "code":
        return "deterministic"
    return None


def _safe(value: Any, depth: int = 0) -> Any:
    """Recursively coerce a node output into JSON-serializable form (and bound size)."""
    if depth > 6:
        return "…"
    if isinstance(value, dict):
        return {str(k): _safe(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v, depth + 1) for v in list(value)[:50]]
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 4000 else value[:4000] + "…"
    content = getattr(value, "content", None)
    if content is not None:  # langchain message-like
        return {"_type": type(value).__name__, "content": _safe(content, depth + 1)}
    return str(value)[:1000]


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


def _summary(node: str, out: dict) -> str:
    try:
        if node == "supervisor":
            return f"→ {out.get('route', '?')}"
        if node == "dsl":
            title = (out.get("deck_spec") or {}).get("title", "?")
            return f"제목: {title} · 슬라이드 {len(out.get('slide_dsls', []) or [])}개"
        if node == "compiler":
            return f"IR {len(out.get('layout_irs', []) or [])}개"
        if node == "render":
            a = out.get("artifact")
            if a:
                return f"완료 · {a['slide_count']}장"
            return os.path.basename(out["output_path"]) if out.get("output_path") else "렌더 실패"
    except Exception:  # noqa: BLE001 - summary is best-effort
        return ""
    return ""


class TraceWriter:
    """Accumulates trace events for one graph run and persists them on flush."""

    def __init__(self, session_id: str, title: str | None = None) -> None:
        self.session_id = session_id
        self.title = title
        self.run_id = uuid4().hex
        self.started_at = datetime.now()
        self.events: list[dict] = []
        self.llm_calls: list[dict] = []
        self.render: dict | None = None

    def add_llm_call(self, record: dict) -> None:
        """Append one LLM-call record (from TracingCallbackHandler)."""
        self.llm_calls.append(record)

    def handle(self, namespace: tuple, data: dict) -> dict | None:
        """Translate one debug-stream item into a trace event (or None to skip)."""
        if not namespace or not str(namespace[0]).startswith("ppt"):
            return None
        kind_type = data.get("type")
        if kind_type not in ("task", "task_result"):
            return None
        payload = data.get("payload") or {}
        name = payload.get("name")
        if not name or name not in NODE_META:
            return None

        kind, label = NODE_META[name]
        event: dict[str, Any] = {
            "run_id": self.run_id,
            "node": name,
            "label": label,
            "kind": kind,
            "tool": _tool_for(kind),
            "step": data.get("step"),
            "ts": str(data.get("timestamp")),
        }
        if kind_type == "task":
            event["status"] = "running"
        else:
            # debug result is the node's returned state delta as a dict
            # (older LangGraph versions emit a list of (channel, value) tuples).
            result = payload.get("result")
            if isinstance(result, dict):
                out = result
            elif isinstance(result, list):
                out = dict(result)
            else:
                out = {}
            error = payload.get("error")
            event["status"] = "error" if error else "done"
            event["summary"] = _summary(name, out)
            event["output"] = _safe(out)
            if error:
                event["error"] = str(error)
            if name == "render":
                report = out.get("render_report")
                if isinstance(report, dict):
                    self.render = report
                # render_node never raises; it returns an apology + issues. Mark the
                # event as an error when no artifact was produced so the trace reflects it.
                if not error and not out.get("artifact"):
                    event["status"] = "error"
        self.events.append(event)
        return event

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

    def _ok(self) -> bool:
        """Whole-run success: no error node events, and render (if attempted) succeeded."""
        if any(e.get("status") == "error" for e in self.events):
            return False
        if self.render is not None:
            return bool(self.render.get("ok"))
        return True


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
