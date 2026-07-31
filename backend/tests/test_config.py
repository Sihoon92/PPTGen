from app.config import Settings


def test_settings_defaults(monkeypatch):
    for key in ("OLLAMA_BASE_URL", "OLLAMA_API_KEY", "OLLAMA_MODEL", "APP_DB_PATH", "CORS_ORIGINS"):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.ollama_api_key == ""
    assert s.ollama_model == "gemma3n:e4b"
    assert s.app_db_path == "./app.db"
    assert s.cors_origins == "http://localhost:5173"


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "custom:tag")
    monkeypatch.setenv("OLLAMA_API_KEY", "secret")
    s = Settings(_env_file=None)
    assert s.ollama_model == "custom:tag"
    assert s.ollama_api_key == "secret"


def test_llm_backend_defaults_to_ollama(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    s = Settings(_env_file=None)
    assert s.llm_backend == "ollama"
    assert s.internal_llm_base_url == ""
    assert s.internal_llm_api_key == ""
    assert s.internal_llm_model == ""


def test_internal_llm_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "internal")
    monkeypatch.setenv("INTERNAL_LLM_BASE_URL", "https://llm.corp.com/v1")
    monkeypatch.setenv("INTERNAL_LLM_API_KEY", "corp-key")
    monkeypatch.setenv("INTERNAL_LLM_MODEL", "corp-gpt")
    s = Settings(_env_file=None)
    assert s.llm_backend == "internal"
    assert s.internal_llm_base_url == "https://llm.corp.com/v1"
    assert s.internal_llm_api_key == "corp-key"
    assert s.internal_llm_model == "corp-gpt"


def test_active_model_follows_backend():
    ollama = Settings(_env_file=None, ollama_model="gemma3n:e4b")
    assert ollama.active_model == "gemma3n:e4b"
    internal = Settings(_env_file=None, llm_backend="internal", internal_llm_model="corp-gpt")
    assert internal.active_model == "corp-gpt"


def test_active_model_internal_fallback_when_model_unset(monkeypatch):
    """active_model must not be empty when llm_backend=internal and INTERNAL_LLM_MODEL is unset."""
    monkeypatch.setenv("LLM_BACKEND", "internal")
    monkeypatch.delenv("INTERNAL_LLM_MODEL", raising=False)
    from app.config import get_settings
    get_settings.cache_clear()
    assert get_settings().active_model == "internal"


def test_active_model_ollama_default(monkeypatch):
    """Ollama backend still returns the configured ollama model."""
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma3n:e4b")
    from app.config import get_settings
    get_settings.cache_clear()
    assert get_settings().active_model == "gemma3n:e4b"
