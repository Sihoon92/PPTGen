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
