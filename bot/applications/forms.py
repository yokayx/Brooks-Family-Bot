from __future__ import annotations

import discord
from sqlalchemy import select

from bot.config import (
    APPLICATION_CLOSED_EMOJI,
    APPLICATION_KIND_COMPOSITIONS,
    APPLICATION_KIND_LABELS,
    APPLICATION_KIND_MAIN,
    APPLICATION_KIND_PANEL_LABELS,
    APPLICATION_KIND_REQUIREMENTS,
    APPLICATION_KIND_ROLE_IDS,
    APPLICATION_KIND_VZP,
    APPLICATION_OPEN_EMOJI,
)
from bot.db import session_scope
from bot.models import ApplicationKind, ApplicationQuestion, BotMessage

OPEN_MARK = APPLICATION_OPEN_EMOJI
CLOSED_MARK = APPLICATION_CLOSED_EMOJI
# Новый вопрос кладём в хвост, потом перенумеруем; снятые живут ещё дальше.
QUESTION_APPEND_ORDER = 10_000
QUESTION_ARCHIVE_ORDER = 100_000


def kind_label(kind: str) -> str:
    return APPLICATION_KIND_LABELS.get(kind, kind)


def panel_label(kind: str) -> str:
    """Имя состава так, как оно написано в панели управления."""
    return APPLICATION_KIND_PANEL_LABELS.get(kind, kind_label(kind))


def status_mark(is_open: bool) -> str:
    return OPEN_MARK if is_open else CLOSED_MARK


def status_text(is_open: bool) -> str:
    """Словами: «Набор открыт» / «Набор закрыт»."""
    return "Набор открыт" if is_open else "Набор закрыт"


def build_applications_text(*, main_open: bool, vzp_open: bool) -> str:
    """Сообщение с меню заявок: два состава, их требования и статус набора."""
    main_role = APPLICATION_KIND_ROLE_IDS[APPLICATION_KIND_MAIN]
    vzp_role = APPLICATION_KIND_ROLE_IDS[APPLICATION_KIND_VZP]

    return (
        "# Оформление заявки в семью\n"
        f"## {APPLICATION_KIND_COMPOSITIONS[APPLICATION_KIND_MAIN]};\n"
        f"## <@&{main_role}>: {APPLICATION_KIND_REQUIREMENTS[APPLICATION_KIND_MAIN]}\n"
        f"> **Статус набора:** {status_mark(main_open)} {status_text(main_open)}\n"
        f"## {APPLICATION_KIND_COMPOSITIONS[APPLICATION_KIND_VZP]};\n"
        f"## <@&{vzp_role}>: {APPLICATION_KIND_REQUIREMENTS[APPLICATION_KIND_VZP]}\n"
        f"> **Статус набора:** {status_mark(vzp_open)} {status_text(vzp_open)}\n"
        "### ```Что важно знать перед подачей:```\n"
        "> • Возраст от 15 лет\n"
        "> • В среднем заявки рассматриваются максимум 1 день.\n"
        "> • Если форму открыть нельзя - значит, набор сейчас приостановлен.\n"
        "> • Не стоит пугаться откатов - это не решающий фактор в принятии/отклонении"
        " Вашей заявки.\n"
        "\n"
        "### ```После подачи заявки:```\n"
        "> • Ваша заявка попадает в канал рассмотрения рекрутов.\n"
        "> • При одобрении вас пригласят на обзвон.\n"
        "> • Следите за личными сообщениями и не закрывайте ЛС от сервера.\n"
        "> • Отвечайте в заявке развёрнуто - это ускоряет рассмотрение.\n"
    )


async def is_kind_open(kind: str) -> bool:
    async with session_scope() as session:
        row = await session.get(ApplicationKind, kind)
        return bool(row.is_open) if row is not None else False


async def set_kind_open(kind: str, is_open: bool) -> None:
    async with session_scope() as session:
        row = await session.get(ApplicationKind, kind)
        if row is None:
            session.add(ApplicationKind(kind=kind, is_open=is_open))
            return
        row.is_open = is_open


async def all_kinds_open() -> dict[str, bool]:
    result: dict[str, bool] = {kind: False for kind in APPLICATION_KIND_LABELS}
    async with session_scope() as session:
        rows = (await session.scalars(select(ApplicationKind))).all()
    for row in rows:
        result[row.kind] = bool(row.is_open)
    return result


async def get_questions(kind: str) -> list[ApplicationQuestion]:
    async with session_scope() as session:
        result = await session.execute(
            select(ApplicationQuestion)
            .where(
                ApplicationQuestion.is_active.is_(True),
                ApplicationQuestion.kind == kind,
            )
            .order_by(ApplicationQuestion.order.asc(), ApplicationQuestion.id.asc())
        )
        return list(result.scalars().all())


async def renumber_questions(kind: str) -> None:
    """Активные вопросы — 1..N по порядку, снятые уносим в хвост (1000+).

    Без этого снятый вопрос сохранял свой старый номер, а активные после него
    съезжали: номера в форме начинали дублироваться и появлялись дырки.
    """
    async with session_scope() as session:
        active_result = await session.execute(
            select(ApplicationQuestion)
            .where(
                ApplicationQuestion.is_active.is_(True),
                ApplicationQuestion.kind == kind,
            )
            .order_by(ApplicationQuestion.order.asc(), ApplicationQuestion.id.asc())
        )
        for index, question in enumerate(active_result.scalars().all(), start=1):
            question.order = index

        inactive_result = await session.execute(
            select(ApplicationQuestion)
            .where(
                ApplicationQuestion.is_active.is_(False),
                ApplicationQuestion.kind == kind,
            )
            .order_by(ApplicationQuestion.id.asc())
        )
        for offset, question in enumerate(inactive_result.scalars().all(), start=1):
            question.order = QUESTION_ARCHIVE_ORDER + offset


async def add_question(kind: str, text: str) -> None:
    """Вопрос в конец списка: сначала хвостовой order, потом перенумерация."""
    async with session_scope() as session:
        session.add(
            ApplicationQuestion(
                order=QUESTION_APPEND_ORDER,
                question=text.strip(),
                is_active=True,
                kind=kind,
            )
        )
    await renumber_questions(kind)


async def remove_question(kind: str, number: int) -> bool:
    """Убрать вопрос по номеру из списка. False — такого номера нет."""
    async with session_scope() as session:
        result = await session.execute(
            select(ApplicationQuestion)
            .where(
                ApplicationQuestion.is_active.is_(True),
                ApplicationQuestion.kind == kind,
            )
            .order_by(ApplicationQuestion.order.asc(), ApplicationQuestion.id.asc())
        )
        questions = list(result.scalars().all())
        if number < 1 or number > len(questions):
            return False
        questions[number - 1].is_active = False
    await renumber_questions(kind)
    return True


async def save_bot_message(name: str, channel_id: int, message_id: int) -> None:
    async with session_scope() as session:
        row = await session.get(BotMessage, name)
        if row is None:
            session.add(BotMessage(name=name, channel_id=channel_id, message_id=message_id))
            return
        row.channel_id = channel_id
        row.message_id = message_id


async def get_bot_message(name: str) -> tuple[int, int] | None:
    async with session_scope() as session:
        row = await session.get(BotMessage, name)
        if row is None or row.channel_id is None or row.message_id is None:
            return None
        return row.channel_id, row.message_id


def build_applications_embed(*, main_open: bool, vzp_open: bool) -> discord.Embed:
    """Меню заявок одним сообщением-эмбедом (текст тот же, что раньше постили)."""
    return discord.Embed(
        title="Оформление заявки в семью",
        description=build_applications_text(main_open=main_open, vzp_open=vzp_open),
        color=discord.Color.from_rgb(88, 101, 242),
    )
