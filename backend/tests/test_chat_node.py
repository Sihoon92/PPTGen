import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import HumanMessage

from app.graph.nodes.chat import make_chat_node


@pytest.mark.asyncio
async def test_chat_node_appends_ai_message():
    fake = GenericFakeChatModel(messages=iter([("Hello there")]))
    node = make_chat_node(fake)
    out = await node({"messages": [HumanMessage("hi")], "mode": "chat", "session_id": "s1"})
    assert "messages" in out
    assert out["messages"][0].content == "Hello there"
