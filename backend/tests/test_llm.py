import pytest

from app.config import Settings
from app.llm import get_chat_model


def test_get_chat_model_uses_settings():
    s = Settings(_env_file=None, ollama_model="gemma3n:e4b",
                 ollama_base_url="http://localhost:11434", ollama_api_key="")
    model = get_chat_model(s)
    assert model.model == "gemma3n:e4b"
    assert "localhost:11434" in model.base_url
    assert model.client_kwargs is None


def test_get_chat_model_sets_auth_header_when_key_present():
    s = Settings(_env_file=None, ollama_api_key="secret-key")
    model = get_chat_model(s)
    headers = (model.client_kwargs or {}).get("headers", {})
    assert headers.get("Authorization") == "Bearer secret-key"


def test_get_chat_model_internal_backend_returns_openai():
    from langchain_openai import ChatOpenAI

    s = Settings(
        _env_file=None,
        llm_backend="internal",
        internal_llm_base_url="https://llm.corp.com/v1",
        internal_llm_api_key="corp-key",
        internal_llm_model="corp-gpt",
    )
    model = get_chat_model(s)
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "corp-gpt"
    assert "llm.corp.com" in str(model.openai_api_base)


def test_get_chat_model_internal_requires_base_url_and_model():
    s = Settings(_env_file=None, llm_backend="internal", internal_llm_model="corp-gpt")
    with pytest.raises(RuntimeError):
        get_chat_model(s)
