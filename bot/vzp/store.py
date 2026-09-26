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
