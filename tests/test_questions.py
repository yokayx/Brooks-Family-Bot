import pytest

from bot.applications import forms
from bot.config import APPLICATION_KIND_MAIN, APPLICATION_KIND_VZP
from bot.db import init_db


@pytest.fixture
async def db(tmp_path):
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'questions.db'}")


async def test_numbering_after_add_and_remove(db) -> None:
    for text in ("Первый", "Второй", "Третий"):
        await forms.add_question(APPLICATION_KIND_MAIN, text)

    questions = await forms.get_questions(APPLICATION_KIND_MAIN)
    assert [q.question for q in questions] == ["Первый", "Второй", "Третий"]
    assert [q.order for q in questions] == [1, 2, 3]

    assert await forms.remove_question(APPLICATION_KIND_MAIN, 2) is True

    questions = await forms.get_questions(APPLICATION_KIND_MAIN)
    assert [q.question for q in questions] == ["Первый", "Третий"]
    assert [q.order for q in questions] == [1, 2]

    # новый вопрос встаёт следующим номером, а не в дырку
    await forms.add_question(APPLICATION_KIND_MAIN, "Четвёртый")

    questions = await forms.get_questions(APPLICATION_KIND_MAIN)
    assert [q.question for q in questions] == ["Первый", "Третий", "Четвёртый"]
    assert [q.order for q in questions] == [1, 2, 3]


async def test_remove_wrong_number_changes_nothing(db) -> None:
    await forms.add_question(APPLICATION_KIND_MAIN, "Один")

    assert await forms.remove_question(APPLICATION_KIND_MAIN, 5) is False
    assert await forms.remove_question(APPLICATION_KIND_MAIN, 0) is False

    questions = await forms.get_questions(APPLICATION_KIND_MAIN)
    assert [q.question for q in questions] == ["Один"]
    assert [q.order for q in questions] == [1]


async def test_no_limit_on_questions(db) -> None:
    for index in range(8):
        await forms.add_question(APPLICATION_KIND_MAIN, f"Вопрос {index}")

    questions = await forms.get_questions(APPLICATION_KIND_MAIN)
    assert len(questions) == 8
    assert [q.order for q in questions] == list(range(1, 9))


async def test_kinds_numbered_independently(db) -> None:
    await forms.add_question(APPLICATION_KIND_MAIN, "Main 1")
    await forms.add_question(APPLICATION_KIND_VZP, "VZP 1")
    await forms.add_question(APPLICATION_KIND_MAIN, "Main 2")

    main_questions = await forms.get_questions(APPLICATION_KIND_MAIN)
    vzp_questions = await forms.get_questions(APPLICATION_KIND_VZP)

    assert [q.question for q in main_questions] == ["Main 1", "Main 2"]
    assert [q.order for q in main_questions] == [1, 2]
    assert [q.question for q in vzp_questions] == ["VZP 1"]
    assert [q.order for q in vzp_questions] == [1]
