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
