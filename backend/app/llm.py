from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama

from app.config import Settings


def get_chat_model(settings: Settings) -> BaseChatModel:
    client_kwargs: dict[str, Any] = {}
    if settings.ollama_api_key:
        client_kwargs["headers"] = {"Authorization": f"Bearer {settings.ollama_api_key}"}
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        client_kwargs=client_kwargs or None,
    )
