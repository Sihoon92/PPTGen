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
