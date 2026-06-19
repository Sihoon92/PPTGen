from dataclasses import dataclass
from typing import Any

from app.config import Settings


@dataclass
class AppState:
    graph: Any
    db_path: str
    settings: Settings
    checkpointer_cm: Any  # the AsyncSqliteSaver context manager (kept to close on shutdown)
