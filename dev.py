"""PPTGen 통합 실행 스크립트 (핫리로드 버전).

백엔드(uvicorn --reload, :8000)와 프론트엔드(vite HMR, :5173)를 동시에 띄우고,
둘 다 준비되면 브라우저를 자동으로 연다. Ctrl+C 하면 둘 다(자식 트리 포함) 종료한다.

핫리로드:
  - 백엔드: backend/app 하위 .py 파일을 저장하면 서버가 자동 재시작.
  - 프론트: vite HMR - 바뀐 모듈만 브라우저에 즉시 반영.

사용법 (아무 파이썬으로나 실행 가능 - 백엔드는 venv 파이썬을 자동으로 찾아 씀):
    python dev.py
"""

import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
IS_WIN = os.name == "nt"

BACKEND_URL = "http://127.0.0.1:8000/"
FRONTEND_URL = "http://localhost:5173/"

# Windows: 자식을 별도 프로세스 그룹으로 띄워 Ctrl+C가 자식에 직접 전달되지 않게 한다.
# 종료는 부모가 KeyboardInterrupt를 받아 taskkill /T 로 트리 전체를 정리한다.
_CREATE_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0

procs: list[subprocess.Popen] = []


def _backend_python() -> str:
    """백엔드 venv의 파이썬 경로 (없으면 현재 파이썬으로 폴백)."""
    venv_py = BACKEND / (".venv/Scripts/python.exe" if IS_WIN else ".venv/bin/python")
    if venv_py.exists():
        return str(venv_py)
    print("[!] backend/.venv 를 못 찾음. 먼저 venv 생성 + 의존성 설치가 필요해:")
    print('    cd backend && python -m venv .venv && .venv\\Scripts\\activate && pip install -e ".[dev]"')
    return sys.executable


def start_backend() -> subprocess.Popen:
    # --reload-dir 로 app/ 만 감시 (app.db 변경에 의한 재시작 폭주 방지)
    return subprocess.Popen(
        [_backend_python(), "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", "8000",
         "--reload", "--reload-dir", str(BACKEND / "app")],
        cwd=str(BACKEND),
        creationflags=_CREATE_GROUP,
    )


def start_frontend() -> subprocess.Popen:
    npm = "npm.cmd" if IS_WIN else "npm"
    return subprocess.Popen(
        [npm, "run", "dev"],
        cwd=str(FRONTEND),
        creationflags=_CREATE_GROUP,
    )


def wait_for(url: str, label: str, timeout: float = 60.0) -> bool:
    """url 이 응답할 때까지 대기 (준비되면 True)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            print(f"[ok] {label} 준비됨 -> {url}")
            return True
        except Exception:
            if any(p.poll() is not None for p in procs):
                return False  # 자식 프로세스가 죽으면 즉시 중단
            time.sleep(1)
    print(f"[!] {label} 가 {int(timeout)}초 안에 안 떴어 -> {url}")
    return False


def stop_all() -> None:
    print("\n[..] 종료 중...")
    for p in procs:
        try:
            if IS_WIN:
                # 자식 트리(reload worker, npm -> node 등)까지 강제 종료
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                               capture_output=True)
            else:
                p.terminate()
        except Exception:
            pass


def main() -> None:
    print("PPTGen 시작 중... (핫리로드 ON)")
    print("  backend  -> http://localhost:8000  (app/ 변경 시 자동 재시작)")
    print("  frontend -> http://localhost:5173  (HMR)")
    print("  (전제: Ollama 실행 중 + backend/.env 의 OLLAMA_MODEL 설정)\n")

    procs.append(start_backend())
    procs.append(start_frontend())

    backend_ok = wait_for(BACKEND_URL, "backend")
    frontend_ok = wait_for(FRONTEND_URL, "frontend")

    if frontend_ok:
        if not backend_ok:
            print("[!] 백엔드가 아직 안 떴어 - UI는 열리지만 /api 호출은 백엔드가 뜰 때까지 실패할 수 있어.")
        print("[->] 브라우저 여는 중...")
        webbrowser.open(FRONTEND_URL)
    else:
        print("[!] 프론트엔드가 안 떠서 브라우저를 안 열었어. 로그를 확인해줘.")

    print("\n둘 다 실행 중 (핫리로드). 종료하려면 Ctrl+C.\n")
    try:
        while True:
            time.sleep(1)
            for p in procs:
                if p.poll() is not None:
                    print("[!] 프로세스 중 하나가 종료됨 - 전체 종료할게.")
                    return
    except KeyboardInterrupt:
        pass
    finally:
        stop_all()


if __name__ == "__main__":
    main()
