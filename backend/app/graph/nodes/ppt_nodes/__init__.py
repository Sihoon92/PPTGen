"""PPT subgraph nodes.

``supervisor`` is the routing hub: every stage returns to it and it picks the next
hop. ``stages`` holds the three work nodes — ``dsl`` (LLM: brief → validated Slide
DSL), ``compiler`` (deterministic: DSL → Layout IR), and ``render`` (Layout IR →
.pptx). Domain logic lives in ``app/ppt/*`` and is reused unchanged.
"""
