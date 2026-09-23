from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.models import Base

engine = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def _ensure_sqlite_dir(url: str) -> None:
    if "sqlite" not in url:
        return
    # sqlite+aiosqlite:///data/brooks.db
    if ":///" in url:
        raw = url.split(":///", 1)[1]
        path = Path(raw)
        if path.parent.parts:
            path.parent.mkdir(parents=True, exist_ok=True)


async def init_db(database_url: str) -> None:
    global engine, SessionLocal
    _ensure_sqlite_dir(database_url)
    engine = create_async_engine(database_url, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_plus_kind)


def _migrate_plus_kind(connection) -> None:
    rows = connection.execute(text("PRAGMA table_info(plus_events)")).fetchall()
    if not rows:
        return
    names = {row[1] for row in rows}
    if "event_kind" not in names:
        connection.execute(
            text("ALTER TABLE plus_events ADD COLUMN event_kind TEXT DEFAULT 'general'")
        )


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    if SessionLocal is None:
        raise RuntimeError("DB is not initialized")
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
