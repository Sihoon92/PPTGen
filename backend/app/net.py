import os

from app.config import Settings

# requests/httpx/openai 가 참조하는 프록시 환경변수 (대소문자 모두)
_PROXY_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)


def apply_proxy_bypass(settings: Settings) -> list[str]:
    """사내 프록시를 우회하도록 HTTP(S)_PROXY 환경변수를 제거한다.

    사내 내부 LLM 엔드포인트는 회사 프록시를 거치면 도달하지 못하는 경우가 많다.
    bypass_proxy=true 이면 프로세스의 프록시 환경변수를 비워(= 수동으로 `set HTTPS_PROXY=`
    한 것과 동일), httpx/openai 등 모든 HTTP 클라이언트가 프록시 없이 직접 연결하게 한다.

    HTTP 클라이언트가 만들어지기 전(startup)에 호출해야 효과가 있다.
    실제로 제거한 변수명 목록을 반환한다(로깅용).
    """
    if not settings.bypass_proxy:
        return []
    cleared: list[str] = []
    for var in _PROXY_VARS:
        if os.environ.pop(var, None) is not None:
            cleared.append(var)
    return cleared
