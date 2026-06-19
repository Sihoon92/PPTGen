import httpx
import pytest

from app.config import Settings
from app.services.ollama_health import check_ollama


@pytest.mark.asyncio
async def test_check_ollama_success(monkeypatch):
    async def fake_get(self, url, *a, **k):
        return httpx.Response(200, json={"models": [{"name": "gemma3n:e4b"}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    result = await check_ollama(Settings(_env_file=None))
    assert result["ok"] is True
    assert "gemma3n:e4b" in result["models"]
    assert result["error"] is None


@pytest.mark.asyncio
async def test_check_ollama_connection_error(monkeypatch):
    async def fake_get(self, url, *a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    result = await check_ollama(Settings(_env_file=None))
    assert result["ok"] is False
    assert result["models"] == []
    assert "refused" in result["error"]


@pytest.mark.asyncio
async def test_check_ollama_http_error(monkeypatch):
    async def fake_get(self, url, *a, **k):
        return httpx.Response(503, json={})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    result = await check_ollama(Settings(_env_file=None))
    assert result["ok"] is False
    assert result["models"] == []
    assert "503" in result["error"]
