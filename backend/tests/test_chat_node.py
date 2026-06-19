import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.graph.nodes.chat import make_chat_node
from app.prompts import CHAT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_chat_node_appends_ai_message():
    fake = GenericFakeChatModel(messages=iter([("Hello there")]))
    node = make_chat_node(fake)
    out = await node({"messages": [HumanMessage("hi")], "mode": "chat", "session_id": "s1"})
    assert "messages" in out
    assert out["messages"][0].content == "Hello there"


_recorded: list = []


class _RecordingModel(BaseChatModel):
    """ainvoke 가 받은 메시지를 모듈 리스트에 기록하는 테스트용 모델."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        _recorded.clear()
        _recorded.extend(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    @property
    def _llm_type(self) -> str:
        return "recording"


@pytest.mark.asyncio
async def test_chat_node_injects_system_prompt_not_persisted():
    _recorded.clear()
    node = make_chat_node(_RecordingModel())
    out = await node({"messages": [HumanMessage("hi")], "mode": "chat", "session_id": "s1"})

    # (a) 모델은 system 프롬프트를 첫 메시지로 받는다.
    assert isinstance(_recorded[0], SystemMessage)
    assert _recorded[0].content == CHAT_SYSTEM_PROMPT
    assert isinstance(_recorded[1], HumanMessage)

    # (b) 반환 상태(=체크포인터에 저장될 값)에는 system 메시지가 없다.
    assert all(not isinstance(m, SystemMessage) for m in out["messages"])
    assert out["messages"][0].content == "ok"
