import httpx
import pytest

from app.config import Settings
from app.services.ollama_health import check_internal_llm, check_llm, check_ollama


def _internal_settings():
    return Settings(
        _env_file=None,
        llm_backend="internal",
        internal_llm_base_url="https://llm.corp.com/v1",
        internal_llm_api_key="corp-key",
        internal_llm_model="corp-gpt",
    )


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


@pytest.mark.asyncio
async def test_check_internal_llm_success(monkeypatch):
    async def fake_get(self, url, *a, **k):
        assert url.endswith("/v1/models")
        return httpx.Response(200, json={"data": [{"id": "corp-gpt"}, {"id": "corp-mini"}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    result = await check_internal_llm(_internal_settings())
    assert result["ok"] is True
    assert result["models"] == ["corp-gpt", "corp-mini"]
    assert result["error"] is None


@pytest.mark.asyncio
async def test_check_internal_llm_http_error(monkeypatch):
    async def fake_get(self, url, *a, **k):
        return httpx.Response(401, json={})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    result = await check_internal_llm(_internal_settings())
    assert result["ok"] is False
    assert result["models"] == []
    assert "401" in result["error"]


@pytest.mark.asyncio
async def test_check_internal_llm_connection_error(monkeypatch):
    async def fake_get(self, url, *a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    result = await check_internal_llm(_internal_settings())
    assert result["ok"] is False
    assert "refused" in result["error"]


@pytest.mark.asyncio
async def test_check_internal_llm_passes_verify_flag(monkeypatch):
    captured = {}
    real_init = httpx.AsyncClient.__init__

    def fake_init(self, *a, **k):
        captured["verify"] = k.get("verify")
        real_init(self, *a, **k)

    async def fake_get(self, url, *a, **k):
        return httpx.Response(200, json={"data": [{"id": "corp-gpt"}]})

    monkeypatch.setattr(httpx.AsyncClient, "__init__", fake_init)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    s = Settings(
        _env_file=None,
        llm_backend="internal",
        internal_llm_base_url="https://llm.corp.com/v1",
        internal_llm_model="corp-gpt",
        internal_llm_verify_ssl=False,
    )
    result = await check_internal_llm(s)
    assert result["ok"] is True
    assert captured["verify"] is False


@pytest.mark.asyncio
async def test_check_internal_llm_missing_base_url():
    s = Settings(_env_file=None, llm_backend="internal")
    result = await check_internal_llm(s)
    assert result["ok"] is False
    assert "INTERNAL_LLM_BASE_URL" in result["error"]


@pytest.mark.asyncio
async def test_check_llm_dispatches_to_internal(monkeypatch):
    async def fake_get(self, url, *a, **k):
        assert "llm.corp.com" in url
        return httpx.Response(200, json={"data": [{"id": "corp-gpt"}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    result = await check_llm(_internal_settings())
    assert result["ok"] is True
    assert result["models"] == ["corp-gpt"]


@pytest.mark.asyncio
async def test_check_llm_dispatches_to_ollama(monkeypatch):
    async def fake_get(self, url, *a, **k):
        assert url.endswith("/api/tags")
        return httpx.Response(200, json={"models": [{"name": "gemma3n:e4b"}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    result = await check_llm(Settings(_env_file=None))
    assert result["ok"] is True
    assert "gemma3n:e4b" in result["models"]
