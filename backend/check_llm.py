r"""사내 LLM 연결 단독 점검 스크립트 (백엔드/프론트 없이 실행).

backend/.env 를 그대로 읽어 아래를 단계별로 시도하고, 어디서·왜 막히는지 출력한다.
  1) 설정/프록시 상태 진단
  2) GET  {base_url}/models           (= 사이드바 "LLM 연결 테스트"가 하는 일)
  3) POST {base_url}/chat/completions (= 실제 답변 생성이 되는지)

사용법:
    cd backend
    .\.venv\Scripts\python.exe check_llm.py

읽는 설정 (backend/.env):
    LLM_BACKEND, INTERNAL_LLM_BASE_URL, INTERNAL_LLM_API_KEY, INTERNAL_LLM_MODEL, BYPASS_PROXY
"""
import os
import sys

import httpx

from app.config import get_settings
from app.net import apply_proxy_bypass

TIMEOUT = 10.0
_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")


def _mask(secret: str) -> str:
    if not secret:
        return "(빈 값)"
    if len(secret) <= 6:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-2:]} (len={len(secret)})"


def _line(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def _try_request(method: str, url: str, headers: dict, json_body=None):
    """verify=True 로 먼저 시도하고, SSL 오류면 verify=False 로 재시도.

    반환: (resp_or_None, error_str_or_None, ssl_bypassed: bool)
    """
    for verify in (True, False):
        try:
            with httpx.Client(timeout=TIMEOUT, verify=verify) as client:
                if method == "GET":
                    resp = client.get(url, headers=headers)
                else:
                    resp = client.post(url, headers=headers, json=json_body)
            return resp, None, (verify is False)
        except Exception as exc:  # noqa: BLE001
            msg = f"{type(exc).__name__}: {exc}"
            is_ssl = "ssl" in msg.lower() or "certificate" in msg.lower()
            if verify is True and is_ssl:
                print("   [!] SSL 인증서 검증 실패 -> verify=False 로 재시도합니다...")
                continue
            return None, msg, False
    return None, "unknown", False


def main() -> int:
    settings = get_settings()

    _line("1) 설정 & 프록시 진단")
    print(f"LLM_BACKEND           : {settings.llm_backend}")
    base = (settings.internal_llm_base_url or "").rstrip("/")
    print(f"INTERNAL_LLM_BASE_URL : {base or '(빈 값)'}")
    print(f"INTERNAL_LLM_MODEL    : {settings.internal_llm_model or '(빈 값)'}")
    print(f"INTERNAL_LLM_API_KEY  : {_mask(settings.internal_llm_api_key)}")
    print(f"BYPASS_PROXY          : {settings.bypass_proxy}")

    print("\n[프록시 환경변수 - bypass 적용 전]")
    pre = [v for v in _PROXY_VARS if os.environ.get(v)]
    print("   " + (", ".join(f"{v}={os.environ[v]}" for v in pre) if pre else "(없음)"))
    cleared = apply_proxy_bypass(settings)
    if cleared:
        print(f"[bypass 적용] 제거됨: {', '.join(cleared)}")
    else:
        print("[bypass 미적용] (BYPASS_PROXY=false 이거나 프록시 변수 없음)")
    print("[프록시 환경변수 - 적용 후]")
    remaining = [v for v in _PROXY_VARS if os.environ.get(v)]
    print("   " + (", ".join(f"{v}={os.environ[v]}" for v in remaining) if remaining else "(없음)"))

    if settings.llm_backend != "internal":
        print("\n[!] LLM_BACKEND 가 'internal' 이 아닙니다. .env 에서 LLM_BACKEND=internal 로 설정 후 다시 실행하세요.")
    if not base or not settings.internal_llm_model:
        print("\n[FAIL] INTERNAL_LLM_BASE_URL / INTERNAL_LLM_MODEL 이 비어 있습니다. .env 를 확인하세요.")
        return 2

    headers = {}
    if settings.internal_llm_api_key:
        headers["Authorization"] = f"Bearer {settings.internal_llm_api_key}"

    results = {}

    # 2) GET /models -- 헬스체크와 동일
    _line("2) GET /models  (사이드바 'LLM 연결 테스트'와 동일)")
    models_url = f"{base}/models"
    print(f"요청: GET {models_url}")
    resp, err, ssl_off = _try_request("GET", models_url, headers)
    if err:
        print(f"[FAIL] {err}")
        results["models"] = False
    else:
        note = " (SSL 검증 끔)" if ssl_off else ""
        print(f"<- HTTP {resp.status_code}{note}")
        body = resp.text[:500]
        if resp.status_code < 400:
            try:
                ids = [m.get("id") for m in resp.json().get("data", [])]
                print(f"[OK] 모델 {len(ids)}개: {ids[:10]}")
                results["models"] = True
            except Exception:  # noqa: BLE001
                print(f"[!] 200 이지만 응답이 예상 형식이 아님:\n   {body}")
                results["models"] = False
        else:
            print(f"[FAIL] 응답 본문:\n   {body}")
            results["models"] = False

    # 3) POST /chat/completions -- 실제 생성
    _line("3) POST /chat/completions  (실제 답변 생성)")
    chat_url = f"{base}/chat/completions"
    payload = {
        "model": settings.internal_llm_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
        "stream": False,
    }
    print(f"요청: POST {chat_url}  (model={settings.internal_llm_model})")
    resp, err, ssl_off = _try_request("POST", chat_url, {**headers, "Content-Type": "application/json"}, payload)
    if err:
        print(f"[FAIL] {err}")
        results["chat"] = False
    else:
        note = " (SSL 검증 끔)" if ssl_off else ""
        print(f"<- HTTP {resp.status_code}{note}")
        body = resp.text[:800]
        if resp.status_code < 400:
            try:
                content = resp.json()["choices"][0]["message"]["content"]
                print(f"[OK] 응답: {content!r}")
                results["chat"] = True
            except Exception:  # noqa: BLE001
                print(f"[!] 200 이지만 응답 파싱 실패:\n   {body}")
                results["chat"] = False
        else:
            print(f"[FAIL] 응답 본문:\n   {body}")
            results["chat"] = False

    # 요약 & 진단
    _line("요약 / 추정 원인")
    print(f"  GET /models : {'OK' if results.get('models') else 'FAIL'}")
    print(f"  POST /chat  : {'OK' if results.get('chat') else 'FAIL'}")
    print()
    if results.get("chat") and not results.get("models"):
        print("=> LLM 자체는 정상인데 /models 만 실패 -> 사내 게이트웨이가 /models 를 지원하지 않을 가능성이 큽니다.")
        print("   이 경우 채팅은 잘 되지만 사이드바 연결 테스트만 빨간불입니다.")
        print("   해결: 헬스체크를 /models 대신 가벼운 chat 호출로 바꾸면 됩니다 (원하면 적용해 드림).")
    elif not results.get("models") and not results.get("chat"):
        print("=> 둘 다 실패. 아래를 순서대로 의심하세요:")
        print("   - base_url 에 /v1 누락 또는 경로 오타 (HTTP 404/405 면 경로 문제)")
        print("   - 인증 실패 (HTTP 401/403 -> 키/헤더 형식)")
        print("   - 프록시: BYPASS_PROXY=true 인데도 위 '적용 후'에 프록시가 남아있다면 그게 원인")
        print("   - 연결 자체 실패(ConnectError/Timeout) -> 사내망 미도달 또는 방화벽")
        print("   - SSL 인증서: 위에서 'verify=False 로 재시도'가 떴다면 사내 MITM 인증서 문제")
    elif results.get("models") and results.get("chat"):
        print("[OK] LLM 연결 정상입니다. 그래도 백엔드를 통한 빨간불이라면 백엔드 실행 시점의 .env/프록시 환경을 확인하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
