from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM backend switch: "ollama" | "internal"
    llm_backend: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_api_key: str = ""
    ollama_model: str = "gemma3n:e4b"
    # Internal OpenAI-compatible API (used when llm_backend == "internal")
    internal_llm_base_url: str = ""
    internal_llm_api_key: str = ""
    internal_llm_model: str = ""
    # 사내 프록시 우회: true 면 startup 에서 HTTP(S)_PROXY 환경변수를 비워 직접 연결한다
    bypass_proxy: bool = False
    app_db_path: str = "./app.db"
    cors_origins: str = "http://localhost:5173"
    # PPT generation
    node_bin: str = "node"
    artifacts_dir: str = "./artifacts"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def active_model(self) -> str:
        """현재 선택된 백엔드의 모델명 (트레이스/로깅용)."""
        if self.llm_backend == "internal":
            return self.internal_llm_model
        return self.ollama_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
