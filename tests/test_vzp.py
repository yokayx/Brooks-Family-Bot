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
