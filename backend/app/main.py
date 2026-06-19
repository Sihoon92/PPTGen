from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.config import get_settings
from app.db.database import init_db
from app.graph.builder import build_graph
from app.llm import get_chat_model
from app.state import AppState


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db(settings.app_db_path)

    cm = AsyncSqliteSaver.from_conn_string(settings.app_db_path)
    async with cm as checkpointer:
        model = get_chat_model(settings)
        graph = build_graph(model, checkpointer)
        app.state.app_state = AppState(
            graph=graph,
            db_path=settings.app_db_path,
            settings=settings,
            checkpointer_cm=cm,
        )
        yield


def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PPTGen Backend", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root():
        return {"status": "ok"}

    # routers registered in later tasks
    from app.api import health, sessions, chat
    app.include_router(health.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")

    return app


app = create_app()
