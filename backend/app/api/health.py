from fastapi import APIRouter, Depends

from app.main import get_app_state
from app.services.ollama_health import check_llm
from app.state import AppState

router = APIRouter()


@router.get("/health/ollama")
async def health_ollama(state: AppState = Depends(get_app_state)):
    # 경로는 프론트 호환을 위해 유지하되, 활성 백엔드(ollama|internal)로 디스패치한다.
    return await check_llm(state.settings)
