from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.config import Settings


def get_chat_model(settings: Settings) -> BaseChatModel:
    """설정의 llm_backend 값에 따라 LLM 클라이언트를 생성한다.

    - "ollama"   : 로컬/원격 Ollama (OLLAMA_* 설정)
    - "internal" : 사내 OpenAI 호환 API (INTERNAL_LLM_* 설정)
    """
    if settings.llm_backend == "internal":
        return _internal_model(settings)
    return _ollama_model(settings)


def _ollama_model(settings: Settings) -> BaseChatModel:
    client_kwargs: dict[str, Any] = {}
    if settings.ollama_api_key:
        client_kwargs["headers"] = {"Authorization": f"Bearer {settings.ollama_api_key}"}
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        client_kwargs=client_kwargs or None,
    )


def _internal_model(settings: Settings) -> BaseChatModel:
    if not settings.internal_llm_base_url or not settings.internal_llm_model:
        raise RuntimeError(
            "LLM_BACKEND=internal 에는 INTERNAL_LLM_BASE_URL 과 INTERNAL_LLM_MODEL 이 필요합니다."
        )
    return ChatOpenAI(
        model=settings.internal_llm_model,
        base_url=settings.internal_llm_base_url,
        # 키가 필요 없는 게이트웨이도 있으므로 빈 값이면 placeholder 사용
        api_key=settings.internal_llm_api_key or "not-needed",
    )
