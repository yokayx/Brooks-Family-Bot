from bot.config import VZP_FAMILY_NAME, VZP_SERVER_NAME


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
