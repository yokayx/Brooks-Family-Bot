from datetime import UTC, datetime, timedelta

from bot.config import VZP_DEF_WINDOW_MINUTES, VZP_FAMILY_NAME, VZP_SERVER_NAME
from bot.vzp.dt import parse_dt


def _norm(value: object) -> str:
    return str(value or "").strip().casefold()


def is_brooks_richman(war: dict) -> bool:
    if _norm(war.get("server_name")) != VZP_SERVER_NAME.casefold():
        return False
    family = VZP_FAMILY_NAME.casefold()
    return _norm(war.get("attacker_name")) == family or _norm(war.get("defender_name")) == family


def brooks_side(war: dict) -> str | None:
    family = VZP_FAMILY_NAME.casefold()
    if _norm(war.get("attacker_name")) == family:
        return "attacker"
    if _norm(war.get("defender_name")) == family:
        return "defender"
    return None


def brooks_won(war: dict) -> bool | None:
    side = brooks_side(war)
    winner = _norm(war.get("winner_side"))
    if side is None or winner not in {"attacker", "defender"}:
        return None
    return winner == side


def is_finished(war: dict) -> bool:
    """Война доиграна.

    В списке `/wars` статус иногда протухает (`active` при доигранном бое),
    поэтому решение принимаем по деталям войны, а не по списку.
    """
    return _norm(war.get("status")) == "finished"


def is_incoming_defense(
    war: dict, *, now: datetime | None = None, window_minutes: int = VZP_DEF_WINDOW_MINUTES
) -> bool:
    """Нам забили деф: Brooks защищается, бой не доигран и начался недавно.

    В списке `/wars` висят протухшие `active`-записи за несколько дней, поэтому
    без окна свежести бот засыпал бы старыми уведомлениями.
    """
    if not is_brooks_richman(war) or is_finished(war):
        return False
    if brooks_side(war) != "defender":
        return False
    started = parse_dt(war.get("started_at"))
    if started is None:
        return False
    current = parse_dt(now) if now is not None else datetime.now(UTC)
    return current - timedelta(minutes=window_minutes) <= started
