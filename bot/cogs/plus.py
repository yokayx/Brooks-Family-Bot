from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.config import RANK_ROLE_IDS
from bot.db import session_scope
from bot.models import PlusEvent
from bot.plus.names import member_game_name
from bot.plus.timeparse import parse_event_time
from bot.roster.manager import is_leader

if TYPE_CHECKING:
    from bot.main import BrooksBot

log = logging.getLogger("brooks.plus")


def _is_family(member: discord.Member) -> bool:
    return any(role.id in RANK_ROLE_IDS for role in member.roles) or is_leader(member)


def _load_participants(raw: str | None) -> dict:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


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
        embed = discord.Embed(
            title="Сбор на мероприятие",
            description=(
                f"**Причина:** {event.reason}\n"
                f"**Время:** <t:{ts}:t> (<t:{ts}:R>)\n"
                f"**Нужен статик:** {'Да' if event.need_static else 'Нет'}"
            ),
            color=discord.Color.from_rgb(88, 101, 242),
        )
        participants = _load_participants(event.participants_json)
        if not participants:
            embed.add_field(name="Участники", value="Пока никто не записался.", inline=False)
            return embed
        lines: list[str] = []
        for index, (user_id, payload) in enumerate(participants.items(), start=1):
            member = guild.get_member(int(user_id))
            if member is None:
                continue
            static = "—"
            if isinstance(payload, dict):
                static = str(payload.get("static") or "—") or "—"
            lines.append(f"{index}. {member_game_name(member)} | {static}")
        embed.add_field(
            name=f"Участники ({len(lines)})",
            value="\n".join(lines)[:1024] if lines else "—",
            inline=False,
        )
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
    async def plus_command(
        self,
        interaction: discord.Interaction,
        причина: str,
        время: str,
        нужен_статик: bool,
    ) -> None:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if interaction.guild is None or member is None:
            await _say(interaction, "Только на сервере.")
            return
        if not is_leader(member):
            await _say(interaction, "У вас нет прав на создание сборов.")
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
            )
            session.add(event)
            await session.flush()
            event_id = event.id

        stored = await self.get_event(event_id)
        if stored is None:
            await interaction.response.send_message("Не удалось создать сбор.", ephemeral=True)
            return
        embed = self.build_embed(interaction.guild, stored)
        await interaction.response.send_message(embed=embed, view=PlusEventView(self))
        message = await interaction.original_response()

        async with session_scope() as session:
            result = await session.execute(select(PlusEvent).where(PlusEvent.id == event_id))
            db_event = result.scalar_one()
            db_event.message_id = message.id


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PlusCog(bot))  # type: ignore[arg-type]
