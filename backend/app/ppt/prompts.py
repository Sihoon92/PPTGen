"""Prompts for the PPT planning LLM nodes.

Kept terse and example-driven on purpose: the target model (``gemma3n:e4b``) is small,
so every prompt demands JSON-only output and shows the exact shape expected.
"""

DECK_SPEC_PROMPT = """You are a presentation planner. From the user's request, produce a deck plan.

Return ONLY a JSON object (no prose, no markdown fences) with this shape:
{{
  "title": "deck title",
  "audience": "who the audience is",
  "goal": "what the deck should achieve",
  "tone": "executive | casual | technical",
  "narrative": ["slide 1 beat", "slide 2 beat", "..."]
}}

The narrative is an ordered list of 4-8 slide beats. Infer reasonable values when the
user is vague. Respond in the user's language.

User request:
{brief}
"""

# Compact catalog the planner must stay within.
PRIMITIVE_CATALOG = """Layout containers and their rules:
- stack: vertical list. props {{"direction":"vertical","weights":[..]?}}. children: any.
- split: two side-by-side regions. props {{"ratio":[a,b]}}. EXACTLY 2 children.
- columns: equal columns. props {{"cols":N}} (2-4). children count == cols.
- grid: rows x cols cells. props {{"cols":N}} (2-4). children: cells.
- kpi_row: a row of metrics. children: all type "metric".
- card: a titled box. content {{"heading": str, "body": {{"type":"bullets","items":[..]}} }}.
- callout: an emphasized line. content {{"text": str}}.
Leaf content primitives (used as children or card bodies):
- text: content {{"text": str}}
- bullets: content {{"items": [str, ...]}} (1-5 short items)
- metric: content {{"label": str, "value": str, "caption": str?}}
- callout: content {{"text": str}}
Every node needs a unique snake_case "id" within its slide. Do NOT include coordinates,
fonts, colors, or sizes."""

DSL_PLANNER_PROMPT = """You design slide layouts. Given the deck plan, produce ALL slides at once.

{catalog}

Return ONLY a JSON array (no prose, no markdown fences). Each slide:
{{
  "slide_id": "s1",
  "role": "cover | comparison | data_story | summary | content",
  "intent": "one-line purpose",
  "title": "slide title",
  "layout": {{ "id": "...", "type": "...", "props": {{}}, "content": {{}}, "children": [] }}
}}

Example single slide (3-column comparison):
{{
  "slide_id": "s1", "role": "comparison", "intent": "compare options",
  "title": "Strategy Comparison",
  "layout": {{
    "id": "cols", "type": "columns", "props": {{"cols": 3}},
    "children": [
      {{"id": "fast", "type": "card", "content": {{"heading": "Fast", "body": {{"type": "bullets", "items": ["MVP first", "Lower cost"]}}}}}},
      {{"id": "quality", "type": "card", "content": {{"heading": "Quality", "body": {{"type": "bullets", "items": ["High polish", "Slower"]}}}}}},
      {{"id": "hybrid", "type": "card", "content": {{"heading": "Hybrid", "body": {{"type": "bullets", "items": ["Balanced", "Recommended"]}}}}}}
    ]
  }}
}}

Make one slide per narrative beat. Keep text concise. Respond in the deck's language.

Deck plan:
{deck_spec}
"""

SUPERVISOR_INTENT_PROMPT = """A presentation deck already exists. The user sent a new request.
Decide which pipeline stage to restart from.

Stages:
- "dsl": the content/structure must change (new slides, different bullets, reordering).
- "compiler": only the layout/arrangement changes (same content, different placement).
- "render": nothing changes; just regenerate the file.

Return ONLY one lowercase word: dsl, compiler, or render.

User request:
{request}
"""

DSL_REPAIR_PROMPT = """Your previous slide JSON had validation problems. Fix them.

{catalog}

Problems to fix:
{issues}

Return ONLY the corrected JSON array of slides (no prose, no markdown fences).

Previous JSON:
{previous}
"""
