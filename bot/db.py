from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

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
