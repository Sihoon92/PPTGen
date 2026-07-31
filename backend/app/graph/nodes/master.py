from app.graph.state import GraphState, Mode


def route_by_mode(state: GraphState) -> Mode:
    """Master router: branch on the requested mode. Unknown modes fall back to chat.

    Extension point: replace/augment with LLM-based intent routing later.
    """
    return "ppt" if state.get("mode") == "ppt" else "chat"
