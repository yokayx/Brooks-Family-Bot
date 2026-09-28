from bot.vzp.filter import brooks_side, brooks_won, is_brooks_richman
from bot.vzp.format import _lines, _num, _our_score, build_result_embed

BROOKS_WIN = {
    "id": "w1",
    "attacker_name": "Brooks",
    "defender_name": "Hellsize",
    "winner_side": "attacker",
    "server_name": "RICHMAN",
    "territory": "Larry's Pork",
    "map_name": "NEW_S_WINDFARM",
    "attacker_score": 4,
    "defender_score": 1,
    "started_at": "2026-09-23T16:25:00.000Z",
    "ended_at": "2026-09-23T16:45:00.000Z",
    "match_skill_tier": "MS",
    "status": "finished",
    "participants": [
        {
            "family_side": "attacker",
            "player_name": "Takashi_Brooks",
            "kills": 3,
            "damage": 900,
            "hit_percent": 26.0,
            "headshot_percent": 5.6,
        },
        {
            "family_side": "attacker",
            "player_name": "Valentin_Brooksov",
            "kills": 1,
            "damage": 200,
            "hit_percent": 20.0,
        },
        {
            "family_side": "defender",
            "player_name": "Enemy_One",
            "kills": 1,
            "damage": 100,
            "hit_percent": 10.0,
        },
    ],
}


def test_filter_brooks_richman_only() -> None:
    assert is_brooks_richman(BROOKS_WIN)
    assert not is_brooks_richman({**BROOKS_WIN, "server_name": "Downtown"})
    assert not is_brooks_richman({**BROOKS_WIN, "attacker_name": "Hellsize", "defender_name": "X"})
    assert is_brooks_richman({**BROOKS_WIN, "attacker_name": "Hellsize", "defender_name": "brooks"})


def test_win_loss_sides() -> None:
    assert brooks_side(BROOKS_WIN) == "attacker"
    assert brooks_won(BROOKS_WIN) is True
    loss = {**BROOKS_WIN, "winner_side": "defender"}
    assert brooks_won(loss) is False
    def_win = {
        **BROOKS_WIN,
        "attacker_name": "Hellsize",
        "defender_name": "Brooks",
        "winner_side": "defender",
    }
    assert brooks_side(def_win) == "defender"
    assert brooks_won(def_win) is True
    assert _our_score(def_win, "defender") == (1, 4)


def test_embed_win() -> None:
    embed = build_result_embed(BROOKS_WIN)
    assert embed.title == "Победа · ATK · Brooks"
    assert "4 : 1" in (embed.description or "")
    assert "ATK" in (embed.description or "")
    # ссылка на конкретную карту войны, а не на страницу семьи
    assert embed.url == "https://vzp-launcher.pro/vzp?war=w1"
    # приписки-футера нет
    assert embed.footer.text is None
    assert embed.timestamp is None
    names = [f.name for f in embed.fields]
    assert any("Brooks" in n for n in names)
    values = "\n".join(f.value for f in embed.fields)
    assert "Takashi_Brooks" in values
    assert "Enemy_One" in values


def test_participant_order() -> None:
    text = _lines(BROOKS_WIN["participants"][:2])
    assert text.index("Takashi_Brooks") < text.index("Valentin_Brooksov")


def test_participant_line_format() -> None:
    text = _lines([BROOKS_WIN["participants"][0]])
    assert text == "3 900 - 26% / 5.6%HS - Takashi_Brooks"

    whole = _num(20.0)
    assert whole == "20"
    assert _num(17.9) == "17.9"


def test_embed_def_loss_side() -> None:
    def_loss = {
        **BROOKS_WIN,
        "id": "w2",
        "attacker_name": "Hellsize",
        "defender_name": "Brooks",
        "winner_side": "attacker",
    }
    embed = build_result_embed(def_loss)
    assert embed.title == "Поражение · DEF · Brooks"
    assert embed.url == "https://vzp-launcher.pro/vzp?war=w2"


def test_incoming_defense_only_fresh_defender_wars() -> None:
    from datetime import UTC, datetime, timedelta

    from bot.vzp.filter import is_incoming_defense

    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    fresh = {
        "server_name": "RICHMAN",
        "attacker_name": "Hellsize",
        "defender_name": "Brooks",
        "status": "active",
        "started_at": "2026-09-26T11:40:00.000Z",
    }
    assert is_incoming_defense(fresh, now=now)

    # мы нападаем — не деф
    assert not is_incoming_defense(
        {**fresh, "attacker_name": "Brooks", "defender_name": "Hellsize"}, now=now
    )
    # чужой сервер
    assert not is_incoming_defense({**fresh, "server_name": "REDWOOD"}, now=now)
    # бой уже доигран
    assert not is_incoming_defense({**fresh, "status": "finished"}, now=now)
    # протухшая active-запись (список такие хранит днями)
    stale = {**fresh, "started_at": "2026-09-23T11:40:00.000Z"}
    assert not is_incoming_defense(stale, now=now)
    # начался только что
    just = {**fresh, "started_at": (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    assert is_incoming_defense(just, now=now)


def test_is_finished_only_by_status() -> None:
    from bot.vzp.filter import is_finished

    assert is_finished(BROOKS_WIN)
    assert not is_finished({**BROOKS_WIN, "status": "active"})
    assert not is_finished({**BROOKS_WIN, "status": None})


async def test_recent_wars_walks_pages_and_dedupes() -> None:
    from bot.vzp.client import VzpClient

    def _page(start: int, count: int) -> dict:
        return {
            "data": [{"id": f"w{start + i}", "server_name": "RICHMAN"} for i in range(count)],
            "total": 999,
        }

    calls: list[dict] = []

    class _Fake(VzpClient):
        async def _get(self, path: str, params: dict | None = None) -> object:
            calls.append(params or {})
            page = int((params or {}).get("page", 1))
            if page == 1:
                return _page(1, 100)
            if page == 2:
                return _page(90, 100)  # 9 дублей с первой страницы
            return _page(300, 5)  # короткая страница — останавливаемся

    wars = await _Fake().recent_wars(pages=5)
    assert len(wars) == 194  # 100 + 89 новых (11 дублей) + 5
    assert [c["page"] for c in calls] == ["1", "2", "3"]
    ids = [w["id"] for w in wars]
    assert len(ids) == len(set(ids))
