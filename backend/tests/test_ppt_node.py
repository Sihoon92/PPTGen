import pytest
from langchain_core.messages import HumanMessage

from app.graph.nodes.ppt import PPT_STUB_MESSAGE, build_ppt_subgraph


@pytest.mark.asyncio
async def test_ppt_subgraph_returns_stub_message():
    graph = build_ppt_subgraph()
    out = await graph.ainvoke(
        {"messages": [HumanMessage("make slides")], "mode": "ppt", "session_id": "s1"}
    )
    assert out["messages"][-1].content == PPT_STUB_MESSAGE
