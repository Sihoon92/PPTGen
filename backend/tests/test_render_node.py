from app.graph.nodes.ppt_nodes.stages import render_node


async def test_render_node_reports_failure_and_dumps_job(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("NODE_BIN", "definitely-not-a-real-binary-xyz")
    state = {
        "session_id": "s1",
        "layout_irs": [{"slide_id": "s1", "elements": []}],
        "theme": {"colors": {"background": "FFFFFF"}},
    }
    config = {"configurable": {"trace_run_id": "run-xyz"}}

    out = await render_node(state, config)

    report = out["render_report"]
    assert report["attempted"] is True
    assert report["ok"] is False
    assert report["job_file"] == "render_job_run-xyz.json"
    assert (tmp_path / "s1" / "render_job_run-xyz.json").exists()
    # pipeline still degrades gracefully
    assert out["messages"]


async def test_render_node_no_slides_reports_not_attempted(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path))
    out = await render_node({"session_id": "s1", "layout_irs": []}, {"configurable": {}})
    assert out["render_report"]["attempted"] is False
