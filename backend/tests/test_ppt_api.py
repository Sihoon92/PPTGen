import itertools
import json
import re

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

import app.graph.nodes.ppt_nodes.stages as stages
import app.main as main_mod
from app.config import get_settings
from app.main import create_app
from app.ppt.renderer import RenderResult

DECK_SPEC_JSON = '{"title":"AI 전략","audience":"임원","goal":"설득","tone":"executive","narrative":["x"]}'
DECK_DSL_JSON = (
    '[{"slide_id":"s1","role":"content","intent":"i","title":"Slide",'
    '"layout":{"id":"root","type":"text","content":{"text":"hi"}}}]'
)


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    async def _render(layout_irs, theme, out_path, node_bin="node", job_dump_path=None):
        return RenderResult(ok=True, out_path=out_path, slide_count=len(layout_irs))

    monkeypatch.setattr(stages, "render_deck", _render)

    real_build = main_mod.build_graph

    def fake_build(model, checkpointer):
        fake = GenericFakeChatModel(messages=itertools.cycle([DECK_SPEC_JSON, DECK_DSL_JSON]))
        return real_build(fake, checkpointer)

    monkeypatch.setattr(main_mod, "build_graph", fake_build)

    app = create_app()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    get_settings.cache_clear()


async def _stream_body(client, method, url, **json_body):
    async with client.stream(method, url, json=json_body) as resp:
        assert resp.status_code == 200
        return "".join([c async for c in resp.aiter_text()])


@pytest.mark.asyncio
async def test_ppt_chat_yields_artifact(client):
    sid = (await client.post("/api/sessions", json={})).json()["id"]

    # one chat turn runs supervisor → dsl → compiler → render → END
    body = await _stream_body(
        client, "POST", f"/api/sessions/{sid}/chat", content="슬라이드 만들어줘", mode="ppt"
    )
    assert "event: artifact" in body
    assert "/api/artifacts/" in body
    assert "event: done" in body
    # planner JSON must NOT leak into the user-facing token stream
    # (it legitimately appears inside `event: node` trace frames).
    token_text = "".join(
        frame for frame in body.split("\n\n") if frame.startswith("event: token")
    )
    assert "slide_id" not in token_text


@pytest.mark.asyncio
async def test_resume_missing_session_404(client):
    resp = await client.post("/api/sessions/nope/resume", json={"answer": "x"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_execution_trace_streamed_and_persisted(client):
    sid = (await client.post("/api/sessions", json={})).json()["id"]
    # detailed brief -> no interrupt -> full pipeline runs
    body = await _stream_body(
        client,
        "POST",
        f"/api/sessions/{sid}/chat",
        content="B2B 경영진 대상으로 AI 도입 효과를 설득하는 발표 자료 만들어줘",
        mode="ppt",
    )
    assert "event: node" in body
    assert "dsl" in body  # a traced node name
    assert "running" in body and "done" in body  # start + complete states

    # persisted trace is retrievable
    trace = (await client.get(f"/api/sessions/{sid}/trace")).json()
    nodes = {e["node"] for e in trace["events"]}
    assert {"supervisor", "dsl", "compiler", "render"} <= nodes
    # completion events carry tool + output
    done_dsl = [e for e in trace["events"] if e["node"] == "dsl" and e["status"] == "done"]
    assert done_dsl and done_dsl[0]["kind"] == "llm"
    # output is captured and non-empty (the validated slide DSLs)
    assert done_dsl[0]["output"].get("slide_dsls")
    # render completion records the produced file path
    done_render = [e for e in trace["events"] if e["node"] == "render" and e["status"] == "done"]
    assert done_render and done_render[0]["output"].get("output_path")


@pytest.mark.asyncio
async def test_trace_also_written_to_human_findable_dir(client, tmp_path):
    sid = (await client.post("/api/sessions", json={})).json()["id"]
    await _stream_body(
        client,
        "POST",
        f"/api/sessions/{sid}/chat",
        content="B2B 경영진 대상으로 AI 도입 효과를 설득하는 발표 자료 만들어줘",
        mode="ppt",
    )
    session_trace = (await client.get(f"/api/sessions/{sid}/trace")).json()

    traces_dir = tmp_path / "artifacts" / "traces"
    # fixed always-latest file mirrors the session's latest trace
    latest = traces_dir / "latest.json"
    assert latest.exists()
    assert json.loads(latest.read_text(encoding="utf-8")) == session_trace

    # a readable history file: <timestamp>_<title-slug>_<runid6>.json
    run6 = session_trace["run_id"][:6]
    history = [
        p for p in traces_dir.glob("*.json")
        if p.name != "latest.json" and run6 in p.name
    ]
    assert len(history) == 1
    name = history[0].name
    assert re.match(r"\d{8}-\d{6}_", name)  # leading timestamp
    assert "발표" in name  # human-readable title slug survived
    # filename is filesystem-safe (no path-unsafe chars)
    assert not set(name) & set('<>:"/\\|?*')


@pytest.mark.asyncio
async def test_trace_missing_session_404(client):
    resp = await client.get("/api/sessions/nope/trace")
    assert resp.status_code == 404
