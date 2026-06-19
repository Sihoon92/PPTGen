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
