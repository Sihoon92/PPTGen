from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

Mode = Literal["chat", "ppt"]


class GraphState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    mode: Mode
    session_id: str
    # Set by the PPT subgraph's finalize node; shared by name so it crosses the
    # subgraph boundary and reaches the SSE layer as an `artifact` event.
    artifact: dict


class PptState(TypedDict, total=False):
    """State for the PPT subgraph.

    Separate from ``GraphState`` on purpose: only ``messages`` and ``session_id``
    overlap by name, so LangGraph maps just those two at the subgraph boundary and
    the pipeline-internal keys never pollute the parent (chat) state. Domain models
    are stored as ``dict`` (``.model_dump()``) to stay JSON-serializable for the
    SQLite checkpointer; nodes re-hydrate with ``Model.model_validate(...)``.
    """

    # boundary keys (shared with GraphState)
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    artifact: dict  # {id, filename, slide_count, download_url} — surfaced to SSE
    # pipeline artifacts
    deck_spec: dict
    slide_dsls: list[dict]
    layout_irs: list[dict]
    theme: dict
    output_path: str
    artifact_id: str
    issues: list[dict]
    # supervisor control
    route: str  # next hop chosen by supervisor; read by the conditional edge
    step_count: int  # loop guard
    pipeline_pos: int  # forward index into [dsl, compiler, render] for this turn
    handled_msg_count: int  # human-message count already consumed (new-turn detection)
