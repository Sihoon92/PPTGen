"""Download endpoint for generated .pptx decks.

Artifacts are resolved by globbing ``<artifacts_dir>/*/deck_<id>.pptx`` — the id is a
uuid4 hex embedded in the filename, so no separate registry/DB is needed. The id is
validated as hex to prevent path traversal.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.main import get_app_state
from app.state import AppState

router = APIRouter()

PPTX_MEDIA = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@router.get("/artifacts/{artifact_id}")
async def download(artifact_id: str, state: AppState = Depends(get_app_state)):
    # uuid4().hex -> only hex chars; reject anything else (defends against traversal).
    if not artifact_id or any(c not in "0123456789abcdef" for c in artifact_id):
        raise HTTPException(status_code=404, detail="artifact not found")

    base = Path(state.settings.artifacts_dir)
    matches = list(base.glob(f"*/deck_{artifact_id}.pptx"))
    if not matches:
        raise HTTPException(status_code=404, detail="artifact not found")

    return FileResponse(str(matches[0]), media_type=PPTX_MEDIA, filename="deck.pptx")
