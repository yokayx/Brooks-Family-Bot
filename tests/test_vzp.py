from bot.vzp.filter import brooks_side, brooks_won, is_brooks_richman
from bot.vzp.format import _lines, _our_score, build_result_embed

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
    assert "Победа" in (embed.title or "")
    assert "4 : 1" in (embed.description or "")
    assert "ATK" in (embed.description or "")
    names = [f.name for f in embed.fields]
    assert any("Brooks" in n for n in names)
    values = "\n".join(f.value for f in embed.fields)
    assert "Takashi_Brooks" in values
    assert "Enemy_One" in values


def test_participant_order() -> None:
    text = _lines(BROOKS_WIN["participants"][:2])
    assert text.index("Takashi_Brooks") < text.index("Valentin_Brooksov")


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
