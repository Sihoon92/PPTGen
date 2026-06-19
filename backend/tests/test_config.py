from app.config import Settings


def test_settings_defaults(monkeypatch):
    for key in ("OLLAMA_BASE_URL", "OLLAMA_API_KEY", "OLLAMA_MODEL", "APP_DB_PATH", "CORS_ORIGINS"):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.ollama_api_key == ""
    assert s.ollama_model == "gemma3n:e4b"
    assert s.app_db_path == "./app.db"


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "custom:tag")
    monkeypatch.setenv("OLLAMA_API_KEY", "secret")
    s = Settings(_env_file=None)
    assert s.ollama_model == "custom:tag"
    assert s.ollama_api_key == "secret"
