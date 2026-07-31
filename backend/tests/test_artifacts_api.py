import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    app = create_app()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_download_existing_artifact(client, tmp_path):
    artifact_id = "abc123def456"
    deck_dir = tmp_path / "artifacts" / "session1"
    deck_dir.mkdir(parents=True)
    (deck_dir / f"deck_{artifact_id}.pptx").write_bytes(b"PK\x03\x04 fake pptx")

    resp = await client.get(f"/api/artifacts/{artifact_id}")
    assert resp.status_code == 200
    assert "presentationml" in resp.headers["content-type"]
    assert resp.content == b"PK\x03\x04 fake pptx"


@pytest.mark.asyncio
async def test_download_missing_artifact_404(client):
    resp = await client.get("/api/artifacts/deadbeef")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_rejects_non_hex_id(client):
    resp = await client.get("/api/artifacts/..%2f..%2fetc")
    assert resp.status_code == 404
