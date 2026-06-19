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
