from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.chat import make_chat_node
from app.graph.nodes.master import route_by_mode
from app.graph.nodes.ppt import build_ppt_subgraph
from app.graph.state import GraphState


async def _master_node(state: GraphState) -> dict:
    """Passthrough router node. Actual branching happens in conditional edges."""
    return {}


def build_graph(model: BaseChatModel, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    sg = StateGraph(GraphState)
    sg.add_node("master", _master_node)
    sg.add_node("chat", make_chat_node(model))
    sg.add_node("ppt", build_ppt_subgraph(model))

    sg.add_edge(START, "master")
    sg.add_conditional_edges("master", route_by_mode, {"chat": "chat", "ppt": "ppt"})
    sg.add_edge("chat", END)
    sg.add_edge("ppt", END)

    return sg.compile(checkpointer=checkpointer)
