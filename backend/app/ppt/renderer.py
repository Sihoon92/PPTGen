"""Python bridge to the Node (PptxGenJS) renderer sidecar.

Spawns ``node render.mjs`` once per deck, pipes the job as JSON on stdin, and parses
the JSON result from stdout. Never raises on a render failure — returns a
``RenderResult`` with ``ok=False`` so the pipeline can record an Issue instead of
breaking the SSE stream.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).parent / "node_renderer" / "render.mjs"


@dataclass
class RenderResult:
    ok: bool
    out_path: str | None = None
    slide_count: int = 0
    error: str | None = None


async def render_deck(
    layout_irs: list[dict[str, Any]],
    theme: dict[str, Any],
    out_path: str,
    node_bin: str = "node",
) -> RenderResult:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    job = json.dumps({"out_path": out_path, "theme": theme, "slides": layout_irs})

    try:
        proc = await asyncio.create_subprocess_exec(
            node_bin,
            str(SCRIPT_PATH),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return RenderResult(ok=False, error=f"node binary not found: {node_bin!r}")

    stdout, stderr = await proc.communicate(job.encode("utf-8"))

    try:
        result = json.loads(stdout.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        err = stderr.decode("utf-8", "replace").strip() or "renderer produced no JSON output"
        return RenderResult(ok=False, error=err[:500])

    if proc.returncode != 0 or not result.get("ok"):
        err = result.get("error") or stderr.decode("utf-8", "replace").strip() or "render failed"
        return RenderResult(ok=False, error=str(err)[:500])

    return RenderResult(
        ok=True,
        out_path=result.get("out_path", out_path),
        slide_count=int(result.get("slide_count", len(layout_irs))),
    )
