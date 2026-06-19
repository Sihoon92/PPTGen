from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from app.graph.state import GraphState

PPT_STUB_MESSAGE = (
    "PPT 생성 기능은 아직 준비 중입니다. 곧 슬라이드를 자동으로 만들어 드릴게요. "
    "지금은 'Chat' 모드에서 대화를 이어가실 수 있어요."
)


async def _ppt_stub_node(state: GraphState) -> dict:
    return {"messages": [AIMessage(content=PPT_STUB_MESSAGE)]}


def build_ppt_subgraph():
    """Single-node stub. Extension point: add outline -> design -> build nodes later."""
    sg = StateGraph(GraphState)
    sg.add_node("ppt_stub", _ppt_stub_node)
    sg.add_edge(START, "ppt_stub")
    sg.add_edge("ppt_stub", END)
    return sg.compile()
