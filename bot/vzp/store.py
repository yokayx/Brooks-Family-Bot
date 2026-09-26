from datetime import UTC, datetime

from sqlalchemy import select

from bot.db import session_scope
from bot.models import PostedVzpWar, VzpDefense


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


async def defense_noticed(war_id: str) -> bool:
    async with session_scope() as session:
        row = await session.get(VzpDefense, war_id)
        return row is not None


async def mark_defense(war_id: str, *, attacker: str, territory: str, event_id: int | None) -> None:
    async with session_scope() as session:
        row = await session.get(VzpDefense, war_id)
        if row is not None:
            return
        session.add(
            VzpDefense(
                war_id=war_id,
                attacker=attacker,
                territory=territory,
                noticed_at=datetime.now(UTC),
                event_id=event_id,
            )
        )
