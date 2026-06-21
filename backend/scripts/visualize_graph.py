"""LangGraph 노드 구조를 Mermaid로 시각화한다.

실행하면:
  1. 전체 그래프(상위: master/chat/ppt, ``ppt`` 서브그래프 내부까지 펼침)와
     PPT 서브그래프 단독 다이어그램을 Mermaid 텍스트로 생성하고
  2. mermaid.js를 임베드한 자체 완결형 HTML을 만들어 기본 브라우저로 열며
  3. Mermaid 소스를 콘솔에도 출력한다(mermaid.live 등에 붙여넣기 용도).

구조만 뽑으므로 실제 LLM/체크포인터는 필요 없다 — 가짜 모델과 인메모리 세이버를 쓴다.

사용법 (backend 디렉터리에서):
    python scripts/visualize_graph.py            # HTML 생성 후 브라우저 열기
    python scripts/visualize_graph.py --no-open  # 열지 않고 파일만 생성
    python scripts/visualize_graph.py --png      # mermaid.ink로 PNG도 저장(인터넷 필요)
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

# `app.*` 절대 임포트가 동작하도록 backend 루트를 경로에 추가한다.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langgraph.checkpoint.memory import MemorySaver

from app.graph.builder import build_graph
from app.graph.nodes.ppt import build_ppt_subgraph

OUT_HTML = BACKEND_ROOT / "artifacts" / "graph_structure.html"

HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PPTGen LangGraph 구조</title>
  <style>
    body {{ font-family: system-ui, "Segoe UI", sans-serif; margin: 0; background: #0f1117; color: #e6e6e6; }}
    header {{ padding: 16px 24px; border-bottom: 1px solid #2a2e3a; }}
    header h1 {{ margin: 0; font-size: 18px; }}
    header p {{ margin: 4px 0 0; color: #9aa0ad; font-size: 13px; }}
    .grid {{ display: flex; flex-wrap: wrap; gap: 24px; padding: 24px; align-items: flex-start; }}
    .panel {{ background: #161922; border: 1px solid #2a2e3a; border-radius: 10px; padding: 16px; flex: 1 1 420px; }}
    .panel h2 {{ margin: 0 0 12px; font-size: 15px; color: #c8ccd6; }}
    .mermaid {{ background: #fff; border-radius: 8px; padding: 12px; overflow: auto; }}
  </style>
</head>
<body>
  <header>
    <h1>PPTGen — LangGraph 노드 구조</h1>
    <p>master → (chat | ppt 서브그래프). 자동 생성됨 · 새로고침하면 갱신됩니다.</p>
  </header>
  <div class="grid">
    <div class="panel">
      <h2>전체 그래프 (ppt 서브그래프 펼침)</h2>
      <pre class="mermaid">{full}</pre>
    </div>
    <div class="panel">
      <h2>PPT 서브그래프 (단독)</h2>
      <pre class="mermaid">{ppt}</pre>
    </div>
  </div>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, theme: "default", securityLevel: "loose" }});
  </script>
</body>
</html>
"""


def _build_graphs():
    """구조만 필요하므로 가짜 모델 + 인메모리 체크포인터로 컴파일한다."""
    fake = GenericFakeChatModel(messages=iter(["_"]))
    full = build_graph(fake, MemorySaver())
    ppt = build_ppt_subgraph(fake)
    return full, ppt


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph 구조를 Mermaid로 시각화")
    parser.add_argument("--no-open", action="store_true", help="브라우저를 열지 않음")
    parser.add_argument("--png", action="store_true", help="mermaid.ink로 PNG도 저장(인터넷 필요)")
    args = parser.parse_args()

    # Windows 콘솔(cp949)에서 한글/이모지 출력이 깨지지 않도록 UTF-8로 전환.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 - 구형 환경에서는 무시
        pass

    full_graph, ppt_graph = _build_graphs()

    # xray=True 로 ppt 서브그래프 내부 노드까지 펼쳐서 그린다.
    full_mermaid = full_graph.get_graph(xray=True).draw_mermaid()
    ppt_mermaid = ppt_graph.get_graph().draw_mermaid()

    print("=" * 70)
    print("전체 그래프 (ppt 서브그래프 펼침)")
    print("=" * 70)
    print(full_mermaid)
    print("=" * 70)
    print("PPT 서브그래프 (단독)")
    print("=" * 70)
    print(ppt_mermaid)

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(
        HTML_TEMPLATE.format(full=full_mermaid, ppt=ppt_mermaid), encoding="utf-8"
    )
    print(f"\n✅ HTML 생성: {OUT_HTML}")

    if args.png:
        try:
            png = full_graph.get_graph(xray=True).draw_mermaid_png()
            png_path = OUT_HTML.with_name("graph_structure.png")
            png_path.write_bytes(png)
            print(f"✅ PNG 생성: {png_path}")
        except Exception as exc:  # noqa: BLE001 - PNG는 부가 기능(네트워크 필요)
            print(f"⚠️  PNG 생성 실패(인터넷/렌더러 필요): {exc}")

    if not args.no_open:
        webbrowser.open(OUT_HTML.as_uri())
        print("🌐 기본 브라우저로 열었습니다.")


if __name__ == "__main__":
    main()
