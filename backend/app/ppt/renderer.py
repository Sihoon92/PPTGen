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
    stack: str | None = None
    stderr: str | None = None


def _parse_render_result(
    stdout: bytes, stderr: bytes, returncode: int, out_path: str
) -> RenderResult:
    """Parse the sidecar's stdout/stderr into a RenderResult.

    Preserves the full JS error message, stack, and stderr (no truncation) so a
    PptxGenJS failure can be diagnosed offline.
    """
    stderr_text = stderr.decode("utf-8", "replace").strip()
    try:
        result = json.loads(stdout.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return RenderResult(
            ok=False,
            error=stderr_text or "renderer produced no JSON output",
            stderr=stderr_text or None,
        )
    if returncode != 0 or not result.get("ok"):
        return RenderResult(
            ok=False,
            error=str(result.get("error") or stderr_text or "render failed"),
            stack=result.get("stack"),
            stderr=stderr_text or None,
        )
    return RenderResult(
        ok=True,
        out_path=result.get("out_path", out_path),
        slide_count=int(result.get("slide_count", 0)),
    )


async def render_deck(
    layout_irs: list[dict[str, Any]],
    theme: dict[str, Any],
    out_path: str,
    node_bin: str = "node",
    job_dump_path: str | None = None,
) -> RenderResult:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    job = json.dumps({"out_path": out_path, "theme": theme, "slides": layout_irs})

    # Persist the exact render input BEFORE spawning so even a crash/hang leaves a
    # reproducible job (`node render.mjs < render_job_*.json`). Best-effort only.
    if job_dump_path:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(job_dump_path)), exist_ok=True)
            with open(job_dump_path, "w", encoding="utf-8") as fh:
                fh.write(job)
        except Exception:  # noqa: BLE001 - tracing must never break render
            pass

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
    result = _parse_render_result(stdout, stderr, proc.returncode, out_path)
    # _parse_render_result sees only the sidecar's JSON; when the renderer omits
    # slide_count on success, fall back to the number of slides we sent.
    if result.ok and not result.slide_count:
        result.slide_count = len(layout_irs)
    return result
