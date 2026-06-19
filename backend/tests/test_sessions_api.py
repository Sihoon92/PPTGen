import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.base import Checkpoint

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


@pytest.mark.asyncio
async def test_delete_missing_returns_404(client):
    r = await client.delete("/api/sessions/nonexistent-id")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_messages_404_for_missing_session(client):
    r = await client.get("/api/sessions/nonexistent-id/messages")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_purges_checkpoint_thread(client):
    """DELETE must remove the LangGraph checkpoint thread, not just the metadata row.

    Steps:
    1. Create a session.
    2. Seed the checkpointer directly with a checkpoint for that thread.
    3. Confirm the checkpoint state is present via aget_state.
    4. DELETE the session via the API.
    5. Assert GET /sessions/{id}/messages returns 404 (metadata gone).
    6. Assert the checkpointer has no state for the thread (checkpoint purged).
    """
    # 1. Create a session
    r = await client.post("/api/sessions", json={"title": "To be deleted"})
    assert r.status_code == 201
    sid = r.json()["id"]

    # Reach the live graph through the ASGI transport's app reference
    transport_app = client._transport.app  # type: ignore[attr-defined]
    graph = transport_app.state.app_state.graph
    checkpointer = graph.checkpointer

    # 2. Seed the checkpointer with a checkpoint for this thread
    cp_id = str(uuid.uuid4())
    checkpoint: Checkpoint = {
        "v": 1,
        "id": cp_id,
        "ts": "2024-01-01T00:00:00+00:00",
        "channel_values": {"messages": []},
        "channel_versions": {},
        "versions_seen": {},
        "pending_sends": [],
    }
    config = {
        "configurable": {
            "thread_id": sid,
            "checkpoint_id": cp_id,
            "checkpoint_ns": "",
        }
    }
    await checkpointer.aput(config, checkpoint, {}, {})

    # 3. Confirm checkpoint state is present (non-empty dict)
    snap_before = await graph.aget_state({"configurable": {"thread_id": sid}})
    assert snap_before.values, (
        f"Expected checkpoint state to be seeded, got: {snap_before.values}"
    )

    # 4. DELETE the session via the API
    r_del = await client.delete(f"/api/sessions/{sid}")
    assert r_del.status_code == 204

    # 5. Messages endpoint now returns 404 (metadata row gone)
    r_msg = await client.get(f"/api/sessions/{sid}/messages")
    assert r_msg.status_code == 404

    # 6. Checkpointer has no state for the thread after adelete_thread
    snap_after = await graph.aget_state({"configurable": {"thread_id": sid}})
    assert not snap_after.values, (
        f"Expected empty checkpoint state after session delete, got: {snap_after.values}"
    )
