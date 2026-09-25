from sqlalchemy import select

from bot.db import session_scope
from bot.models import PostedVzpWar


async def already_posted(war_id: str) -> bool:
    async with session_scope() as session:
        row = await session.get(PostedVzpWar, war_id)
        return row is not None


async def mark_posted(war_id: str, message_id: int | None) -> None:
    async with session_scope() as session:
        row = await session.get(PostedVzpWar, war_id)
        if row is None:
            session.add(PostedVzpWar(war_id=war_id, message_id=message_id))
            return
        row.message_id = message_id


async def has_any_posted() -> bool:
    async with session_scope() as session:
        row = (await session.scalars(select(PostedVzpWar.war_id).limit(1))).first()
        return row is not None


async def mark_many_seen(war_ids: list[str]) -> None:
    if not war_ids:
        return
    async with session_scope() as session:
        q = select(PostedVzpWar.war_id).where(PostedVzpWar.war_id.in_(war_ids))
        existing = set((await session.scalars(q)).all())
        for war_id in war_ids:
            if war_id not in existing:
                session.add(PostedVzpWar(war_id=war_id, message_id=None))
