from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.config import (
    HEAD_VZP_ROLE_ID,
    PLUS_KIND_GENERAL,
    PLUS_KIND_LABELS,
    PLUS_KIND_PINGS,
    PLUS_KIND_VZP,
    RANK_ROLE_IDS,
)
from bot.db import session_scope
from bot.models import PlusEvent
from bot.plus.names import participant_line
from bot.plus.timeparse import parse_event_time
from bot.roster.manager import is_leader

if TYPE_CHECKING:
    from bot.main import BrooksBot

log = logging.getLogger("brooks.plus")


def _is_family(member: discord.Member) -> bool:
    return any(role.id in RANK_ROLE_IDS for role in member.roles) or is_leader(member)


def _can_create_plus(member: discord.Member) -> bool:
    return any(role.id == HEAD_VZP_ROLE_ID for role in member.roles) or is_leader(member)


def _kind_label(kind: str | None) -> str:
    return PLUS_KIND_LABELS.get(kind or PLUS_KIND_GENERAL, "Общий")


def _load_participants(raw: str | None) -> dict:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


# Поле эмбеда — 1024 символа, держим запас.
FIELD_LIMIT = 1000


def _chunk_lines(lines: list[str], limit: int = FIELD_LIMIT) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    size = 0
    for line in lines:
        extra = len(line) + (1 if current else 0)
        if current and size + extra > limit:
            chunks.append(current)
            current = [line]
            size = len(line)
        else:
            current.append(line)
            size += extra
    if current:
        chunks.append(current)
    return chunks


def _safe_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _static_of(payload: object) -> str:
    if isinstance(payload, dict):
        return str(payload.get("static") or "").strip() or "—"
    return "—"


async def _say(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.send_message(text, ephemeral=True)


class StaticModal(discord.ui.Modal):
    def __init__(self, cog: PlusCog, event_id: int) -> None:
        super().__init__(title="Указать статик")
        self.cog = cog
        self.event_id = event_id
        self.static = discord.ui.TextInput(label="Статик", max_length=100)
        self.add_item(self.static)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.add_participant(interaction, self.event_id, str(self.static).strip())


class PlusEventView(discord.ui.View):
    def __init__(self, cog: PlusCog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    async def _event(self, interaction: discord.Interaction) -> PlusEvent | None:
        mid = interaction.message.id if interaction.message else 0
        event = await self.cog.get_event_from_message(mid)
        if event is None or not event.is_active:
            await _say(interaction, "Сбор не найден или уже закрыт.")
            return None
        return event

    @discord.ui.button(label="➕ Плюс", style=discord.ButtonStyle.success, custom_id="plus:join")
    async def plus_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        event = await self._event(interaction)
        if event is None:
            return
        if event.need_static:
            await interaction.response.send_modal(StaticModal(self.cog, event.id))
            return
        await self.cog.add_participant(interaction, event.id, None)

    @discord.ui.button(label="➖ Минус", style=discord.ButtonStyle.danger, custom_id="plus:leave")
    async def minus_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        event = await self._event(interaction)
        if event is None:
            return
        await self.cog.remove_participant(interaction, event.id)


class PlusCog(commands.Cog, name="Plus"):
    """Сборы: /плюсы, кнопки плюс/минус, опциональный статик."""

    def __init__(self, bot: BrooksBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(PlusEventView(self))

    async def get_event(self, event_id: int) -> PlusEvent | None:
        async with session_scope() as session:
            result = await session.execute(select(PlusEvent).where(PlusEvent.id == event_id))
            return result.scalar_one_or_none()

    async def get_event_from_message(self, message_id: int) -> PlusEvent | None:
        async with session_scope() as session:
            stmt = select(PlusEvent).where(PlusEvent.message_id == message_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    def build_embed(self, guild: discord.Guild, event: PlusEvent) -> discord.Embed:
        when = event.event_time
        ts = int(when.timestamp()) if when is not None else 0
        kind = getattr(event, "event_kind", None) or PLUS_KIND_GENERAL
        label = _kind_label(kind)
        color = (
            discord.Color.from_rgb(192, 57, 43)
            if kind == PLUS_KIND_VZP
            else discord.Color.from_rgb(88, 101, 242)
        )
        embed = discord.Embed(
            title=f"Сбор · {label}",
            description=(
                f"**Тип:** {label}\n"
                f"**Причина:** {event.reason}\n"
                f"**Время:** <t:{ts}:t> (<t:{ts}:R>)\n"
                f"**Нужен статик:** {'Да' if event.need_static else 'Нет'}"
            ),
            color=color,
        )
        participants = _load_participants(event.participants_json)
        if not participants:
            embed.add_field(name="Участники", value="Пока никто не записался.", inline=False)
            return embed
        entries: list[tuple[discord.Member, object]] = []
        for user_id, payload in participants.items():
            member_id = _safe_int(user_id)
            if member_id is None:
                continue
            member = guild.get_member(member_id)
            if member is None:
                continue
            entries.append((member, payload))

        lines = [
            participant_line(index, member, _static_of(payload))
            for index, (member, payload) in enumerate(entries, start=1)
        ]
        if not lines:
            embed.add_field(name="Участники", value="Пока никто не записался.", inline=False)
            return embed

        chunks = _chunk_lines(lines)
        for index, chunk in enumerate(chunks, start=1):
            title = f"Участники ({len(lines)})"
            if len(chunks) > 1:
                title = f"{title} · {index}/{len(chunks)}"
            embed.add_field(name=title, value="\n".join(chunk), inline=False)
        return embed

    async def update_event_message(self, event_id: int) -> None:
        event = await self.get_event(event_id)
        if event is None or event.message_id is None:
            return
        channel = self.bot.get_channel(event.channel_id)
        if not isinstance(channel, discord.TextChannel):
            try:
                fetched = await self.bot.fetch_channel(event.channel_id)
            except discord.HTTPException:
                log.exception("plus channel %s missing", event.channel_id)
                return
            if not isinstance(fetched, discord.TextChannel):
                return
            channel = fetched
        try:
            message = await channel.fetch_message(event.message_id)
        except discord.HTTPException:
            log.exception("cannot fetch plus message %s", event.message_id)
            return
        embed = self.build_embed(channel.guild, event)
        await message.edit(embed=embed, view=PlusEventView(self))

    async def add_participant(
        self,
        interaction: discord.Interaction,
        event_id: int,
        static_name: str | None,
    ) -> None:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if interaction.guild is None or member is None:
            await _say(interaction, "Только на сервере.")
            return
        if not _is_family(member):
            await _say(interaction, "Записываться могут только члены семьи.")
            return

        async with session_scope() as session:
            result = await session.execute(select(PlusEvent).where(PlusEvent.id == event_id))
            event = result.scalar_one_or_none()
            if event is None or not event.is_active:
                await _say(interaction, "Сбор не найден или закрыт.")
                return
            people = _load_participants(event.participants_json)
            people[str(member.id)] = {"user_id": member.id, "static": static_name or ""}
            event.participants_json = json.dumps(people, ensure_ascii=False)

        await self.update_event_message(event_id)
        text = "Вы записаны на событие."
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)

    async def remove_participant(self, interaction: discord.Interaction, event_id: int) -> None:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None:
            await _say(interaction, "Не удалось определить участника.")
            return

        async with session_scope() as session:
            result = await session.execute(select(PlusEvent).where(PlusEvent.id == event_id))
            event = result.scalar_one_or_none()
            if event is None or not event.is_active:
                await _say(interaction, "Сбор не найден или закрыт.")
                return
            people = _load_participants(event.participants_json)
            people.pop(str(member.id), None)
            event.participants_json = json.dumps(people, ensure_ascii=False)

        await self.update_event_message(event_id)
        await interaction.response.send_message("Вы убраны из списка участников.", ephemeral=True)

    @app_commands.command(name="плюсы", description="Создать сбор на мероприятие")
    @app_commands.describe(
        тип="Общий или VZP — от этого зависит тег роли",
        причина="Зачем сбор",
        время="ЧЧ:ММ по Москве",
        нужен_статик="Спрашивать статик при записи (необязательно)",
    )
    @app_commands.choices(
        тип=[
            app_commands.Choice(name="Общий", value=PLUS_KIND_GENERAL),
            app_commands.Choice(name="VZP", value=PLUS_KIND_VZP),
        ]
    )
    async def plus_command(
        self,
        interaction: discord.Interaction,
        тип: app_commands.Choice[str],
        причина: str,
        время: str,
        нужен_статик: bool = False,
    ) -> None:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if interaction.guild is None or member is None:
            await _say(interaction, "Только на сервере.")
            return
        if not _can_create_plus(member):
            await _say(interaction, "Сборы создаёт Head VZP или руководство.")
            return
        try:
            event_time = parse_event_time(время)
        except ValueError as error:
            await _say(interaction, str(error))
            return
        if interaction.channel_id is None:
            await _say(interaction, "Нет канала.")
            return

        async with session_scope() as session:
            event = PlusEvent(
                channel_id=interaction.channel_id,
                creator_id=member.id,
                reason=причина,
                event_time=event_time,
                need_static=нужен_статик,
                participants_json="{}",
                is_active=True,
                event_kind=тип.value,
            )
            session.add(event)
            await session.flush()
            event_id = event.id

        stored = await self.get_event(event_id)
        if stored is None:
            await interaction.response.send_message("Не удалось создать сбор.", ephemeral=True)
            return
        embed = self.build_embed(interaction.guild, stored)
        ping_role = PLUS_KIND_PINGS.get(тип.value)
        ping = f"<@&{ping_role}>" if ping_role else None
        mentions = discord.AllowedMentions(everyone=False, users=False, roles=True)
        await interaction.response.send_message(
            content=ping,
            embed=embed,
            view=PlusEventView(self),
            allowed_mentions=mentions,
        )
        message = await interaction.original_response()

        async with session_scope() as session:
            result = await session.execute(select(PlusEvent).where(PlusEvent.id == event_id))
            db_event = result.scalar_one()
            db_event.message_id = message.id


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PlusCog(bot))  # type: ignore[arg-type]
