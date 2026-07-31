import json
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.api.sse import format_sse
from app.constants import DEFAULT_SESSION_TITLE
from app.db import sessions_repo as repo
from app.main import get_app_state
from app.ppt.trace import TraceWriter, TracingCallbackHandler
from app.schemas import ChatBody, ResumeBody
from app.state import AppState

router = APIRouter()


def _derive_title(text: str) -> str:
    text = text.strip().replace("\n", " ")
    return (text[:40] + "…") if len(text) > 40 else (text or DEFAULT_SESSION_TITLE)


async def stream_graph(
    graph: Any, inputs: Any, cfg: dict, session_id: str, title: str | None = None
) -> AsyncIterator[str]:
    """Run the graph and translate its stream into SSE frames.

    Streamed with ``subgraphs=True`` so PPT-subgraph inner nodes are visible. Frames:
    - ``token``  : assistant text (restricted to the ``chat`` node so PPT planner JSON
                   never leaks; PPT user-facing text comes from ``finalize`` via updates)
    - ``interrupt``: pipeline paused awaiting a user answer
    - ``artifact``: a downloadable deck is ready
    - ``node``   : per-node execution trace (running/done/error + tool + output) for the
                   debug view; also persisted to a per-run JSON file
    - ``done`` / ``error``: terminal
    """
    tracer = TraceWriter(session_id, title)
    handler = TracingCallbackHandler(tracer)
    cfg = {
        **cfg,
        "callbacks": [handler],
        "configurable": {**(cfg.get("configurable") or {}), "trace_run_id": tracer.run_id},
    }
    streamed_chat = False
    artifact_sent = False
    interrupt_sent = False
    try:
        async for namespace, mode, data in graph.astream(
            inputs, cfg, stream_mode=["messages", "updates", "debug"], subgraphs=True
        ):
            if mode == "messages":
                chunk, meta = data
                if meta.get("langgraph_node") != "chat":
                    continue
                text = getattr(chunk, "content", "")
                if text:
                    streamed_chat = True
                    yield format_sse("token", {"delta": text})

            elif mode == "updates":
                items = list((data or {}).items())
                for node, node_out in items:
                    if node == "__interrupt__" and not interrupt_sent:
                        interrupt_sent = True
                        yield format_sse("interrupt", {"interrupt": node_out[0].value})
                if namespace == ():  # top-level: artifact + user-facing messages live here
                    for node, node_out in items:
                        if not isinstance(node_out, dict):
                            continue
                        if node_out.get("artifact") and not artifact_sent:
                            artifact_sent = True
                            yield format_sse("artifact", {"artifact": node_out["artifact"]})
                        if node == "chat" and streamed_chat:
                            continue
                        for m in node_out.get("messages", []) or []:
                            content = getattr(m, "content", "")
                            if content:
                                yield format_sse("token", {"delta": content})

            elif mode == "debug":
                event = tracer.handle(namespace, data)
                if event:
                    yield format_sse("node", event)

        yield format_sse("done", {"session_id": session_id})
    except Exception as exc:  # noqa: BLE001 - report streaming failures to the client
        yield format_sse("error", {"message": str(exc)})
    finally:
        tracer.flush()


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, body: ChatBody, state: AppState = Depends(get_app_state)):
    session = await repo.get_session(state.db_path, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    if session["title"] == DEFAULT_SESSION_TITLE:
        title = _derive_title(body.content)
        await repo.rename_session(state.db_path, session_id, title)
    else:
        title = session["title"]
        await repo.touch_session(state.db_path, session_id)

    cfg = {"configurable": {"thread_id": session_id}}
    inputs = {
        "messages": [HumanMessage(content=body.content)],
        "mode": body.mode,
        "session_id": session_id,
    }
    return StreamingResponse(
        stream_graph(state.graph, inputs, cfg, session_id, title),
        media_type="text/event-stream",
    )


@router.post("/sessions/{session_id}/resume")
async def resume(session_id: str, body: ResumeBody, state: AppState = Depends(get_app_state)):
    """Resume a graph paused on an interrupt (e.g. the PPT deck-intent question)."""
    session = await repo.get_session(state.db_path, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    await repo.touch_session(state.db_path, session_id)

    cfg = {"configurable": {"thread_id": session_id}}
    return StreamingResponse(
        stream_graph(state.graph, Command(resume=body.answer), cfg, session_id, session["title"]),
        media_type="text/event-stream",
    )


@router.get("/sessions/{session_id}/trace")
async def get_trace(session_id: str, state: AppState = Depends(get_app_state)):
    """Return the latest persisted execution trace for a session (debug view)."""
    path = Path(state.settings.artifacts_dir) / session_id / "trace_latest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no trace for session")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
