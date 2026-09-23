import json

from bot.db import session_scope
from bot.models import RosterState

STATE_ROW_ID = 1


async def load_state() -> tuple[bool, list[int]]:
    async with session_scope() as session:
        row = await session.get(RosterState, STATE_ROW_ID)
        if row is None:
            row = RosterState(id=STATE_ROW_ID, fail_state=False, message_ids="[]")
            session.add(row)
            await session.flush()
            return False, []
        try:
            ids = [int(x) for x in json.loads(row.message_ids)]
        except (TypeError, ValueError, json.JSONDecodeError):
            ids = []
        return row.fail_state, ids


async def save_state(*, fail_state: bool, message_ids: list[int]) -> None:
    payload = json.dumps(message_ids)
    async with session_scope() as session:
        row = await session.get(RosterState, STATE_ROW_ID)
        if row is None:
            session.add(
                RosterState(id=STATE_ROW_ID, fail_state=fail_state, message_ids=payload)
            )
            return
        row.fail_state = fail_state
        row.message_ids = payload


async def set_fail_state(fail_state: bool) -> None:
    async with session_scope() as session:
        row = await session.get(RosterState, STATE_ROW_ID)
        if row is None:
            session.add(RosterState(id=STATE_ROW_ID, fail_state=fail_state, message_ids="[]"))
            return
        row.fail_state = fail_state
        if fail_state:
            row.message_ids = "[]"
