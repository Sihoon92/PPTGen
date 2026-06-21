"""PPT subgraph assembly — supervisor hub + three work nodes.

    START → supervisor ─route─▶ dsl ──────┐
                │        ─route─▶ compiler─┤  (each stage returns to supervisor)
                │        ─route─▶ render ──┘
                └──────── route=end ─▶ END

The supervisor picks the next hop each visit; ``dsl → compiler → render`` runs by a
forward pointer (see ``ppt_nodes/supervisor.py``). Stages reuse the deterministic
domain logic in ``app/ppt/*`` (``ppt_nodes/stages.py``).

Compiled WITHOUT a checkpointer — the parent graph's AsyncSqliteSaver owns
persistence across the subgraph boundary.
"""

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.ppt_nodes.stages import compiler_node, make_dsl_node, render_node
from app.graph.nodes.ppt_nodes.supervisor import (
    make_supervisor_node,
    route_from_supervisor,
)
from app.graph.state import PptState


def build_ppt_subgraph(model: BaseChatModel) -> CompiledStateGraph:
    sg = StateGraph(PptState)

    sg.add_node("supervisor", make_supervisor_node(model))
    sg.add_node("dsl", make_dsl_node(model))
    sg.add_node("compiler", compiler_node)
    sg.add_node("render", render_node)

    sg.add_edge(START, "supervisor")
    sg.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {"dsl": "dsl", "compiler": "compiler", "render": "render", "end": END},
    )
    sg.add_edge("dsl", "supervisor")
    sg.add_edge("compiler", "supervisor")
    sg.add_edge("render", "supervisor")

    return sg.compile()
