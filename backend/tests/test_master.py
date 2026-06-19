from app.graph.nodes.master import route_by_mode


def test_route_to_chat():
    assert route_by_mode({"mode": "chat", "messages": [], "session_id": "s1"}) == "chat"


def test_route_to_ppt():
    assert route_by_mode({"mode": "ppt", "messages": [], "session_id": "s1"}) == "ppt"


def test_route_defaults_to_chat_for_unknown():
    assert route_by_mode({"mode": "weird", "messages": [], "session_id": "s1"}) == "chat"
