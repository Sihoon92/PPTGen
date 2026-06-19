import itertools

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
        fake = GenericFakeChatModel(messages=itertools.cycle(["Hello world"]))
        return real_build(fake, checkpointer)

    monkeypatch.setattr(main_mod, "build_graph", fake_build)

    app = create_app()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
async def client_and_app(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))

    real_build = main_mod.build_graph

    def fake_build(model, checkpointer):
        fake = GenericFakeChatModel(messages=itertools.cycle(["Hello world"]))
        return real_build(fake, checkpointer)

    monkeypatch.setattr(main_mod, "build_graph", fake_build)

    app = create_app()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, app


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


@pytest.mark.asyncio
async def test_chat_missing_session_returns_404(client):
    resp = await client.post(
        "/api/sessions/does-not-exist/chat",
        json={"content": "hi", "mode": "chat"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_streams_error_on_exception(client_and_app, monkeypatch):
    client, app = client_and_app
    sid = (await client.post("/api/sessions", json={})).json()["id"]

    async def boom(*args, **kwargs):
        raise RuntimeError("boom")
        yield  # make this an async generator

    monkeypatch.setattr(app.state.app_state.graph, "astream", boom)
    async with client.stream(
        "POST", f"/api/sessions/{sid}/chat", json={"content": "x", "mode": "chat"}
    ) as resp:
        body = "".join([c async for c in resp.aiter_text()])
    assert "event: error" in body
    assert "boom" in body
