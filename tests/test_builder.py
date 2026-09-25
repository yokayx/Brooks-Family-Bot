from types import SimpleNamespace

from bot.config import FALLBACK_NICK, RANK_ROLES
from bot.roster.builder import _split_section, build_roster

OWNER = RANK_ROLES[0][0]
DEP = RANK_ROLES[2][0]
MAIN = RANK_ROLES[7][0]


def _member(
    user_id: int,
    nick: str | None,
    role_ids: list[int],
    *,
    bot: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        nick=nick,
        display_name=nick or "User",
        bot=bot,
        roles=[SimpleNamespace(id=rid) for rid in role_ids],
    )


def test_header_unique_count_and_multi_role() -> None:
    members = [
        _member(1, "[Klyde] | Илья", [OWNER, MAIN]),
        _member(2, "[Alpha] | A", [MAIN]),
        _member(3, "nope", [MAIN]),
    ]
    payload = build_roster(members)
    assert payload.unique_count == 3
    assert payload.messages[0] == "# Состав Brooks\n## Численность: 3"
    owner_msg = next(m for m in payload.messages if m.startswith("## Owner"))
    main_msg = next(m for m in payload.messages if m.startswith("## Main"))
    assert "<@1> | Klyde Brooks" in owner_msg
    assert "<@1> | Klyde Brooks" in main_msg
    assert "<@3> | " + FALLBACK_NICK in main_msg


def test_empty_ranks_omitted() -> None:
    members = [_member(1, "[Klyde] | x", [OWNER])]
    payload = build_roster(members)
    joined = "\n".join(payload.messages)
    assert "## Owner" in joined
    assert "## Main" not in joined
    assert "## Test" not in joined


def test_sort_case_insensitive() -> None:
    members = [
        _member(10, "[bob] | x", [MAIN]),
        _member(11, "[Alice] | x", [MAIN]),
        _member(12, "[alice] | x", [MAIN]),
    ]
    payload = build_roster(members)
    main_msg = next(m for m in payload.messages if m.startswith("## Main"))
    lines = [line for line in main_msg.splitlines() if line.startswith("<@")]
    assert lines[0].startswith("<@11>")
    assert lines[1].startswith("<@12>")
    assert lines[2].startswith("<@10>")


def test_bots_and_unrelated_skipped() -> None:
    members = [
        _member(1, "[Bot] | x", [MAIN], bot=True),
        _member(2, "[Guest] | x", [999]),
    ]
    payload = build_roster(members)
    assert payload.unique_count == 0
    assert len(payload.messages) == 1


def test_split_section_repeats_heading() -> None:
    lines = [f"<@{i}> | Name{i}" for i in range(80)]
    chunks = _split_section("Main", lines, limit=200)
    assert len(chunks) > 1
    assert all(c.startswith("## Main\n") for c in chunks)
    assert sum(c.count("<@") for c in chunks) == 80


def test_pipe_nick_without_brackets() -> None:
    members = [
        _member(1, "Klyde | Илья", [MAIN]),
        _member(2, "[Brooks] Alpha | A", [MAIN]),
    ]
    payload = build_roster(members)
    main_msg = next(m for m in payload.messages if m.startswith("## Main"))
    assert "<@1> | Klyde Brooks" in main_msg
    assert "<@2> | Alpha" in main_msg
