import asyncio

import pytest

from app.db.database import init_db
from app.db import sessions_repo as repo


@pytest.fixture
async def db(tmp_path):
    path = str(tmp_path / "test.db")
    await init_db(path)
    return path


@pytest.mark.asyncio
async def test_create_and_get(db):
    s = await repo.create_session(db, title="First")
    assert s["title"] == "First"
    assert s["mode"] == "chat"
    fetched = await repo.get_session(db, s["id"])
    assert fetched["id"] == s["id"]


@pytest.mark.asyncio
async def test_list_orders_newest_first(db):
    a = await repo.create_session(db, title="A")
    b = await repo.create_session(db, title="B")
    await asyncio.sleep(0.001)
    await repo.touch_session(db, a["id"])  # bump A
    ids = [s["id"] for s in await repo.list_sessions(db)]
    assert ids[0] == a["id"]
    assert ids[1] == b["id"]


@pytest.mark.asyncio
async def test_rename(db):
    s = await repo.create_session(db, title="Old")
    await asyncio.sleep(0.001)
    updated = await repo.rename_session(db, s["id"], "New")
    assert updated["title"] == "New"
    assert updated["updated_at"] > s["updated_at"]


@pytest.mark.asyncio
async def test_delete(db):
    s = await repo.create_session(db, title="X")
    assert await repo.delete_session(db, s["id"]) is True
    assert await repo.get_session(db, s["id"]) is None
