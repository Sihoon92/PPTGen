from fastapi import APIRouter, Depends

from app.main import get_app_state
from app.services.ollama_health import check_ollama
from app.state import AppState

router = APIRouter()


@router.get("/health/ollama")
async def health_ollama(state: AppState = Depends(get_app_state)):
    return await check_ollama(state.settings)
