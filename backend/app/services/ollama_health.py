import httpx

from app.config import Settings


async def check_ollama(settings: Settings) -> dict:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    headers = {}
    if settings.ollama_api_key:
        headers["Authorization"] = f"Bearer {settings.ollama_api_key}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code >= 400:
            return {
                "ok": False,
                "models": [],
                "error": f"HTTP {resp.status_code}",
            }
        data = resp.json()
        models = [m["name"] for m in data.get("models", []) if m.get("name")]
        return {"ok": True, "models": models, "error": None}
    except Exception as exc:  # noqa: BLE001 - surface any connectivity problem to the UI
        return {"ok": False, "models": [], "error": str(exc)}
