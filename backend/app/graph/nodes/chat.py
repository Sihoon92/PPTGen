from typing import Awaitable, Callable

from langchain_core.language_models import BaseChatModel

from app.graph.state import GraphState

ChatNode = Callable[[GraphState], Awaitable[dict]]


def make_chat_node(model: BaseChatModel) -> ChatNode:
    async def chat_node(state: GraphState) -> dict:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response]}

    return chat_node
