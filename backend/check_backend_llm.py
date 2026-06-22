r"""백엔드 '실제 코드 경로'로 LLM 연결을 점검한다 (프론트엔드 없이).

check_llm.py 와의 차이:
  - check_llm.py 는 자체 raw httpx + 'SSL 실패 시 verify=False 재시도' 로직 → 설정과 무관하게 통과.
  - 이 스크립트는 백엔드가 실제로 쓰는 함수를 그대로 호출한다:
      apply_proxy_bypass(settings)        (lifespan 과 동일)
      check_llm(settings)                 (= 사이드바 'LLM 연결 테스트'가 실행하는 바로 그 코드)
      get_chat_model(settings).ainvoke()  (= 채팅 노드의 실제 답변 생성 경로)
    따라서 이게 통과하면 백엔드(빨간불/채팅)도 동일하게 동작한다.

사용법:
    cd backend
    .\.venv\Scripts\python.exe check_backend_llm.py
"""
import asyncio

from langchain_core.messages import HumanMessage

from app.config import get_settings
from app.llm import get_chat_model
from app.net import apply_proxy_bypass, resolve_ssl_verify
from app.services.ollama_health import check_llm


async def main() -> None:
    s = get_settings()

    print("=" * 60)
    print("백엔드가 실제로 읽은 설정 (backend/.env)")
    print("=" * 60)
    print(f"llm_backend            : {s.llm_backend}")
    print(f"internal_llm_base_url  : {s.internal_llm_base_url or '(빈 값)'}")
    print(f"internal_llm_model     : {s.internal_llm_model or '(빈 값)'}")
    print(f"internal_llm_verify_ssl: {s.internal_llm_verify_ssl}")
    print(f"internal_llm_ca_bundle : {s.internal_llm_ca_bundle or '(없음)'}")
    print(f"bypass_proxy           : {s.bypass_proxy}")
    print(f"-> resolve_ssl_verify  : {resolve_ssl_verify(s)}   (헬스체크/LLM이 쓰는 verify 값)")

    cleared = apply_proxy_bypass(s)
    print(f"-> 프록시 제거         : {cleared or '(없음)'}")

    # 1) 헬스체크: 빨간불이 실행하는 바로 그 코드
    print("\n" + "=" * 60)
    print("[1] check_llm(settings)  == 사이드바 'LLM 연결 테스트' 와 동일 ==")
    print("=" * 60)
    health = await check_llm(s)
    print(f"결과: {health}")
    if not health.get("ok"):
        print(">> 빨간불의 '실제 원인'이 위 error 에 그대로 나옵니다. (프론트는 점만 보여줘서 안 보였던 메시지)")

    # 2) 실제 생성 경로: 채팅 노드가 쓰는 model.ainvoke
    print("\n" + "=" * 60)
    print("[2] get_chat_model(settings).ainvoke()  == 채팅 실제 생성 경로 ==")
    print("=" * 60)
    try:
        model = get_chat_model(s)
        resp = await model.ainvoke([HumanMessage(content="ping")])
        text = getattr(resp, "content", resp)
        print(f"[OK] 응답: {text!r}"[:200])
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {type(exc).__name__}: {exc}")

    print("\n" + "=" * 60)
    print("해석")
    print("=" * 60)
    print("- [1] ok=True 인데 앱은 빨간불  -> 실행 중인 백엔드가 stale(미재시작). dev.py 완전 재시작 필요.")
    print("- [1] ok=False                 -> 위 error 가 진짜 원인 (SSL/프록시/경로/인증).")
    print("- [1] ok=True 이고 앱도 정상    -> 프론트(브라우저)에서 다시 '연결 테스트' 클릭.")


if __name__ == "__main__":
    asyncio.run(main())
