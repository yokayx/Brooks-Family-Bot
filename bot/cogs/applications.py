from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from bot.applications import forms
from bot.applications.dates import parse_date
from bot.config import (
    APPLICATION_ACCEPT_ROLE_IDS,
    APPLICATION_KIND_MAIN,
    APPLICATION_KIND_PANEL_LABELS,
    APPLICATION_KIND_VZP,
    APPLICATION_MAX_QUESTIONS,
    APPLICATION_PING_ROLE_IDS,
    APPLICATIONS_CHANNEL_ID,
    APPLICATIONS_MESSAGE_KEY,
    CLOSED_TICKETS_CATEGORY_ID,
    CONTROL_MESSAGE_KEY,
    CONTROL_PANEL_CHANNEL_ID,
    LEADERSHIP_ROLE_IDS,
    MOSCOW_TZ,
    RANK_ROLE_IDS,
    RECRUITER_ROLE_ID,
    TICKETS_CATEGORY_ID,
)
from bot.db import session_scope
from bot.models import ApplicationQuestion, Birthday, Ticket
from bot.roster.manager import is_leader

if TYPE_CHECKING:
    from bot.main import BrooksBot

log = logging.getLogger("brooks.applications")
MSK = ZoneInfo(MOSCOW_TZ)
OPEN_STATUSES = ("open", "claimed", "accepted_pending_close")
NICK_FORM = "`[Nick] | Имя`"


def _is_family(member: discord.Member) -> bool:
    return any(role.id in RANK_ROLE_IDS for role in member.roles) or is_leader(member)


def _is_staff(member: discord.Member) -> bool:
    return is_leader(member) or any(role.id == RECRUITER_ROLE_ID for role in member.roles)


def _as_msk(stamp: datetime) -> datetime:
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(MSK)


def _embed(title: str, description: str = "", *, footer: str | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.from_rgb(88, 101, 242),
    )
    if footer:
        embed.set_footer(text=footer)
    return embed


def _answers_embed(title: str, answers: list[dict]) -> discord.Embed:
    """Анкета заявителя полями вопрос -> ответ."""
    embed = _embed(title)
    for answer in answers:
        question = str(answer.get("question") or "Вопрос")[:256]
        value = str(answer.get("answer") or "").strip() or "—"
        embed.add_field(name=question, value=value[:1024], inline=False)
    return embed


async def _say(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.send_message(text, ephemeral=True)


class ApplicationsCog(commands.Cog, name="Applications"):
    """Заявки в семью: форма, тикеты, принять/отклонить. Без ЧС."""

    def __init__(self, bot: BrooksBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(ApplicationSelectView(self))
        self.bot.add_view(ControlPanelView(self))
        self.bot.add_view(ClaimTicketView(self))
        self.bot.add_view(ManagedTicketView(self))
        self.bot.add_view(PostAcceptView(self))
        asyncio.create_task(self._startup_publish())

    async def _resolve_text_channel(self, channel_id: int) -> discord.TextChannel | None:
        """Канал ищем и в кэше, и запросом к API — иначе «канал не найден»."""
        channel = self.bot.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        try:
            fetched = await self.bot.fetch_channel(channel_id)
        except discord.HTTPException:
            log.exception("cannot resolve channel %s", channel_id)
            return None
        if isinstance(fetched, discord.TextChannel):
            return fetched
        return None

    def _staff_roles(self, guild: discord.Guild) -> list[discord.Role]:
        wanted = (*LEADERSHIP_ROLE_IDS, RECRUITER_ROLE_ID)
        roles: list[discord.Role] = []
        for role_id in wanted:
            role = guild.get_role(role_id)
            if role is not None:
                roles.append(role)
        return roles

    async def get_active_questions(
        self, kind: str = APPLICATION_KIND_MAIN
    ) -> list[ApplicationQuestion]:
        return await forms.get_questions(kind)

    async def refresh_applications_message(self) -> None:
        """Статусы набора меняются с панели — перерисовываем меню заявок."""
        await self.ensure_applications_message()

    async def _startup_publish(self) -> None:
        """Меню заявок и панель управления публикуются сами, без команд."""
        await self.bot.wait_until_ready()
        await self.ensure_applications_message()
        await self.ensure_control_panel()

    async def ensure_applications_message(self) -> None:
        """Меню заявок: обновляем, а если сообщение пропало — отправляем заново."""
        status = await forms.all_kinds_open()
        embed = forms.build_applications_embed(
            main_open=status[APPLICATION_KIND_MAIN],
            vzp_open=status[APPLICATION_KIND_VZP],
        )
        await self._ensure_message(
            APPLICATIONS_MESSAGE_KEY,
            APPLICATIONS_CHANNEL_ID,
            embed,
            lambda: ApplicationSelectView(self),
        )

    async def ensure_control_panel(self) -> None:
        """Панель управления: обновляем, а если сообщение пропало — отправляем заново."""
        status = await forms.all_kinds_open()
        embed = _embed(
            "Панель управления",
            forms.build_control_panel_description(
                main_open=status[APPLICATION_KIND_MAIN],
                vzp_open=status[APPLICATION_KIND_VZP],
            ),
            footer="Одна кнопка на функцию: нажал — включил, нажал ещё раз — выключил.",
        )
        await self._ensure_message(
            CONTROL_MESSAGE_KEY,
            CONTROL_PANEL_CHANNEL_ID,
            embed,
            lambda: ControlPanelView(self),
        )

    async def _ensure_message(
        self,
        key: str,
        channel_id: int,
        embed: discord.Embed,
        view_factory: Callable[[], discord.ui.View],
    ) -> None:
        stored = await forms.get_bot_message(key)
        if stored is not None:
            stored_channel_id, message_id = stored
            channel = await self._resolve_text_channel(stored_channel_id)
            if channel is not None:
                try:
                    message = await channel.fetch_message(message_id)
                except discord.HTTPException:
                    log.warning("%s: сообщение %s не найдено, отправим заново", key, message_id)
                else:
                    await message.edit(embed=embed, view=view_factory())
                    return

        channel = await self._resolve_text_channel(channel_id)
        if channel is None:
            log.error("%s: канал %s недоступен", key, channel_id)
            return
        message = await channel.send(embed=embed, view=view_factory())
        await forms.save_bot_message(key, channel.id, message.id)
        log.info("%s: опубликовано в %s", key, channel_id)

    async def get_ticket_for_channel(self, channel_id: int) -> Ticket | None:
        async with session_scope() as session:
            result = await session.execute(select(Ticket).where(Ticket.channel_id == channel_id))
            return result.scalar_one_or_none()

    async def get_ticket(self, ticket_id: int) -> Ticket | None:
        async with session_scope() as session:
            result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
            return result.scalar_one_or_none()

    async def render_questions_embed(self, kind: str = APPLICATION_KIND_MAIN) -> discord.Embed:
        questions = await self.get_active_questions(kind)
        description = (
            "\n".join(f"**{question.order}.** {question.question}" for question in questions)
            or "Вопросы пока не добавлены."
        )
        return _embed(
            f"Форма заявок · {forms.kind_label(kind)}",
            description,
            footer=f"Максимум {APPLICATION_MAX_QUESTIONS} активных вопросов одновременно.",
        )

    async def ensure_can_apply(self, interaction: discord.Interaction) -> tuple[bool, str | None]:
        if interaction.guild is None:
            return False, "Команда доступна только на сервере."
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None:
            return False, "Не удалось определить участника."
        if _is_family(member):
            return False, "У вас уже есть семейная роль, заявка не требуется."

        async with session_scope() as session:
            open_result = await session.execute(
                select(Ticket).where(
                    Ticket.applicant_id == member.id,
                    Ticket.status.in_(OPEN_STATUSES),
                )
            )
            if open_result.scalar_one_or_none() is not None:
                return False, "У вас уже есть открытая заявка."

            latest_result = await session.execute(
                select(Ticket)
                .where(Ticket.applicant_id == member.id)
                .order_by(Ticket.created_at.desc())
                .limit(1)
            )
            latest = latest_result.scalar_one_or_none()
            if latest is not None and latest.created_at is not None:
                last_time = _as_msk(latest.created_at)
                now = datetime.now(UTC).astimezone(MSK)
                if now - last_time < timedelta(hours=24):
                    return False, "После прошлой подачи ещё не прошло 24 часа."

        return True, None

    async def create_ticket_channel(
        self, guild: discord.Guild, member: discord.Member
    ) -> discord.TextChannel:
        category = guild.get_channel(TICKETS_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            raise RuntimeError("Не найдена категория открытых тикетов")

        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
        }
        me = guild.me
        if me is not None:
            overwrites[me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
            )
        for role in self._staff_roles(guild):
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            )

        safe_name = f"заявка-{member.display_name}".lower().replace(" ", "-")[:80]
        return await guild.create_text_channel(
            name=safe_name,
            category=category,
            overwrites=overwrites,
            reason=f"Новая заявка от {member}",
        )

    async def create_ticket(
        self,
        channel: discord.TextChannel,
        member: discord.Member,
        answers: list[dict],
        kind: str = APPLICATION_KIND_MAIN,
    ) -> Ticket:
        async with session_scope() as session:
            existing = await session.execute(select(Ticket).where(Ticket.channel_id == channel.id))
            record = existing.scalar_one_or_none()
            if record is not None:
                return record
            ticket = Ticket(
                channel_id=channel.id,
                applicant_id=member.id,
                kind=kind,
                status="open",
                answers_json=json.dumps(answers, ensure_ascii=False),
                created_at=datetime.now(UTC),
            )
            session.add(ticket)
            await session.flush()
            await session.refresh(ticket)
            return ticket

    async def open_application_ticket(
        self, guild: discord.Guild, member: discord.Member, kind: str
    ) -> discord.TextChannel:
        """Тикет сразу: внутрь кладём эмбед с формой заявки, дальше человек пишет сам."""
        questions = await self.get_active_questions(kind)
        channel = await self.create_ticket_channel(guild, member)
        ticket = await self.create_ticket(channel, member, [], kind)

        embed = _embed(
            f"Новая заявка · {forms.kind_label(kind)}",
            f"Заявитель: {member.mention}\nТикет: #{ticket.id}",
        )
        if questions:
            embed.add_field(
                name="Форма заявки",
                value="\n".join(
                    f"**{question.order}.** {question.question}" for question in questions
                ),
                inline=False,
            )
            embed.set_footer(text="Ответы напишите в этот канал — по одному на вопрос, по порядку.")
        else:
            embed.set_footer(text="Вопросы формы не настроены.")

        await channel.send(embed=embed, view=ClaimTicketView(self))
        return channel

    async def _mark_replied(self, ticket_id: int) -> None:
        async with session_scope() as session:
            result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
            ticket = result.scalar_one_or_none()
            if ticket is not None:
                ticket.applicant_replied = True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Заявитель написал в тикете — тегаем рекрутов. Один раз на заявку."""
        if message.guild is None or message.author.bot:
            return
        ticket = await self.get_ticket_for_channel(message.channel.id)
        if ticket is None or ticket.status not in OPEN_STATUSES:
            return
        if ticket.applicant_id != message.author.id or ticket.applicant_replied:
            return

        await self._mark_replied(ticket.id)
        ping = " ".join(f"<@&{role_id}>" for role_id in APPLICATION_PING_ROLE_IDS)
        await message.channel.send(f"{ping} — {message.author.mention} заполнил анкету.")

    async def close_ticket(self, ticket_id: int, *, accepted: bool) -> None:
        guild = await self._guild()
        if guild is None:
            return

        async with session_scope() as session:
            result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
            ticket = result.scalar_one_or_none()
            if ticket is None:
                return

            channel = guild.get_channel(ticket.channel_id)
            member = guild.get_member(ticket.applicant_id)
            closed_category = guild.get_channel(CLOSED_TICKETS_CATEGORY_ID)

            if isinstance(channel, discord.TextChannel):
                try:
                    if member is not None:
                        await channel.set_permissions(member, overwrite=None)
                    if isinstance(closed_category, discord.CategoryChannel):
                        await channel.edit(category=closed_category)
                except discord.HTTPException:
                    log.exception("cannot archive ticket %s", ticket.id)

            ticket.status = "accepted_closed" if accepted else "rejected"
            ticket.closed_at = datetime.now(UTC)

    async def schedule_close(self, ticket_id: int) -> None:
        await asyncio.sleep(3600)
        ticket = await self.get_ticket(ticket_id)
        if ticket is None or ticket.status != "accepted_pending_close":
            return
        await self.close_ticket(ticket_id, accepted=True)

    async def _save_birthday(self, channel_id: int, day: int, month: int) -> bool:
        async with session_scope() as session:
            ticket_result = await session.execute(
                select(Ticket).where(Ticket.channel_id == channel_id)
            )
            ticket = ticket_result.scalar_one_or_none()
            if ticket is None:
                return False
            result = await session.execute(
                select(Birthday).where(Birthday.user_id == ticket.applicant_id)
            )
            record = result.scalar_one_or_none()
            if record is None:
                session.add(Birthday(user_id=ticket.applicant_id, day=day, month=month))
            else:
                record.day = day
                record.month = month
            return True

    async def _guild(self) -> discord.Guild | None:
        channel = self.bot.get_channel(APPLICATIONS_CHANNEL_ID)
        if isinstance(channel, discord.abc.GuildChannel):
            return channel.guild
        try:
            fetched = await self.bot.fetch_channel(APPLICATIONS_CHANNEL_ID)
        except discord.HTTPException:
            log.exception("cannot resolve guild from applications channel")
            return None
        if isinstance(fetched, discord.abc.GuildChannel):
            return fetched.guild
        return None

    @app_commands.command(name="настроить-форму", description="Настроить вопросы формы заявки")
    @app_commands.describe(вид="Main — фракционные мероприятия, VZP — только ВЗП")
    @app_commands.choices(
        вид=[
            app_commands.Choice(name="Main", value=APPLICATION_KIND_MAIN),
            app_commands.Choice(name="VZP", value=APPLICATION_KIND_VZP),
        ]
    )
    async def configure_form(
        self, interaction: discord.Interaction, вид: app_commands.Choice[str]
    ) -> None:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None or not is_leader(member):
            await _say(interaction, "Нет прав.")
            return
        embed = await self.render_questions_embed(вид.value)
        await interaction.response.send_message(
            embed=embed, view=QuestionManagerView(self, вид.value), ephemeral=True
        )


class ApplicationSelectView(discord.ui.View):
    """Меню заявок: Young (Main) или Test (VZP). Живёт после рестарта."""

    def __init__(self, cog: ApplicationsCog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.select(
        custom_id="applications:kind",
        placeholder="Выберите, какую заявку подать",
        options=[
            discord.SelectOption(
                label="Заявка на Young",
                description="Заполнить заявку в семью.",
                value=APPLICATION_KIND_MAIN,
            ),
            discord.SelectOption(
                label="Заявка на Test",
                description="Заполнить заявку в семью на VZP.",
                value=APPLICATION_KIND_VZP,
            ),
        ],
    )
    async def choose(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        kind = select.values[0] if select.values else APPLICATION_KIND_MAIN
        if not await forms.is_kind_open(kind):
            await _say(interaction, "Набор на этот состав сейчас приостановлен.")
            return
        can_apply, reason = await self.cog.ensure_can_apply(interaction)
        if not can_apply:
            await _say(interaction, reason or "Заявку подать нельзя.")
            return
        if interaction.guild is None:
            await _say(interaction, "Заявку можно подать только на сервере.")
            return
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None:
            await _say(interaction, "Не удалось определить участника.")
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            channel = await self.cog.open_application_ticket(interaction.guild, member, kind)
        except Exception:
            log.exception("cannot open application ticket for %s", member.id)
            await interaction.followup.send("Не удалось создать канал заявки.", ephemeral=True)
            return
        await interaction.followup.send(f"Заявка создана: {channel.mention}", ephemeral=True)


class ControlPanelView(discord.ui.View):
    """Панель управления: одна кнопка на функцию — включает/выключает по нажатию."""

    def __init__(self, cog: ApplicationsCog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    async def _leader(self, interaction: discord.Interaction) -> bool:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None or not is_leader(member):
            await _say(interaction, "Нет прав.")
            return False
        return True

    async def _toggle(self, interaction: discord.Interaction, kind: str) -> None:
        if not await self._leader(interaction):
            return
        is_open = await forms.is_kind_open(kind)
        await forms.set_kind_open(kind, not is_open)
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.cog.ensure_control_panel()
        await self.cog.ensure_applications_message()
        state = "выключен" if is_open else "включён"
        await interaction.followup.send(
            f"Набор {forms.panel_label(kind)}: {state}.", ephemeral=True
        )

    async def _form(self, interaction: discord.Interaction, kind: str) -> None:
        if not await self._leader(interaction):
            return
        embed = await self.cog.render_questions_embed(kind)
        await interaction.response.send_message(
            embed=embed, view=QuestionManagerView(self.cog, kind), ephemeral=True
        )

    @discord.ui.button(
        label=f"Набор {APPLICATION_KIND_PANEL_LABELS[APPLICATION_KIND_MAIN]}",
        style=discord.ButtonStyle.primary,
        custom_id="control:main:toggle",
        row=0,
    )
    async def toggle_main(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._toggle(interaction, APPLICATION_KIND_MAIN)

    @discord.ui.button(
        label=f"Набор {APPLICATION_KIND_PANEL_LABELS[APPLICATION_KIND_VZP]}",
        style=discord.ButtonStyle.primary,
        custom_id="control:vzp:toggle",
        row=0,
    )
    async def toggle_vzp(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._toggle(interaction, APPLICATION_KIND_VZP)

    @discord.ui.button(
        label=f"Форма {APPLICATION_KIND_PANEL_LABELS[APPLICATION_KIND_MAIN]}",
        style=discord.ButtonStyle.secondary,
        custom_id="control:main:form",
        row=1,
    )
    async def form_main(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._form(interaction, APPLICATION_KIND_MAIN)

    @discord.ui.button(
        label=f"Форма {APPLICATION_KIND_PANEL_LABELS[APPLICATION_KIND_VZP]}",
        style=discord.ButtonStyle.secondary,
        custom_id="control:vzp:form",
        row=1,
    )
    async def form_vzp(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._form(interaction, APPLICATION_KIND_VZP)


class ClaimTicketView(discord.ui.View):
    def __init__(self, cog: ApplicationsCog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Взять заявку",
        style=discord.ButtonStyle.primary,
        custom_id="applications:claim",
    )
    async def claim(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None or not _is_staff(member):
            await _say(interaction, "Эта кнопка доступна только руководству и рекрутерам.")
            return
        if interaction.channel is None:
            await _say(interaction, "Не удалось определить канал тикета.")
            return

        async with session_scope() as session:
            result = await session.execute(
                select(Ticket).where(Ticket.channel_id == interaction.channel.id)
            )
            ticket = result.scalar_one_or_none()
            if ticket is None:
                await _say(interaction, "Тикет не найден.")
                return
            if ticket.handler_id is not None:
                await _say(interaction, "Заявка уже закреплена за другим стаффом.")
                return
            ticket.handler_id = member.id
            ticket.status = "claimed"
            ticket.claimed_at = datetime.now(UTC)

        embed = None
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0].copy()
            embed.add_field(name="Взял заявку", value=member.mention, inline=False)

        await interaction.response.edit_message(embed=embed, view=ManagedTicketView(self.cog))
        await interaction.followup.send(f"Заявка закреплена за {member.mention}.")


class ManagedTicketView(discord.ui.View):
    def __init__(self, cog: ApplicationsCog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    async def _load_ticket(self, interaction: discord.Interaction) -> Ticket | None:
        if interaction.channel is None:
            return None
        return await self.cog.get_ticket_for_channel(interaction.channel.id)

    async def _check_actor(
        self, interaction: discord.Interaction, ticket: Ticket | None
    ) -> tuple[bool, str | None]:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None or ticket is None:
            return False, "Тикет не найден."
        if ticket.handler_id == member.id or is_leader(member):
            return True, None
        return False, "Управлять заявкой может только тот, кто её взял, или руководство."

    @discord.ui.button(
        label="Освободить заявку",
        style=discord.ButtonStyle.secondary,
        custom_id="applications:release",
    )
    async def release(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        ticket = await self._load_ticket(interaction)
        allowed, message = await self._check_actor(interaction, ticket)
        if not allowed or ticket is None:
            await _say(interaction, message or "Недостаточно прав.")
            return

        async with session_scope() as session:
            result = await session.execute(select(Ticket).where(Ticket.id == ticket.id))
            db_ticket = result.scalar_one()
            db_ticket.handler_id = None
            db_ticket.status = "open"
            db_ticket.claimed_at = None

        embed = None
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0].copy()
            embed.clear_fields()
            source = interaction.message.embeds[0]
            for field in source.fields:
                if field.name == "Взял заявку":
                    continue
                embed.add_field(name=field.name, value=field.value, inline=field.inline)

        await interaction.response.edit_message(embed=embed, view=ClaimTicketView(self.cog))
        await interaction.followup.send("Заявка освобождена.")

    @discord.ui.button(
        label="Принять заявку",
        style=discord.ButtonStyle.success,
        custom_id="applications:accept",
    )
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        ticket = await self._load_ticket(interaction)
        allowed, message = await self._check_actor(interaction, ticket)
        if not allowed or ticket is None or interaction.guild is None:
            await _say(interaction, message or "Недостаточно прав.")
            return

        member = interaction.guild.get_member(ticket.applicant_id)
        if member is None:
            await _say(interaction, "Заявитель не найден на сервере.")
            return

        roles_to_add: list[discord.Role] = []
        for role_id in APPLICATION_ACCEPT_ROLE_IDS:
            role = interaction.guild.get_role(role_id)
            if role is not None:
                roles_to_add.append(role)
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Заявка в семью принята")
            except discord.HTTPException:
                log.exception("cannot grant accept roles to %s", member.id)

        welcome = (
            f"Ваша заявка одобрена! Смените никнейм по форме {NICK_FORM} и укажите день рождения."
        )
        try:
            await member.send(welcome)
        except discord.HTTPException:
            log.warning("cannot DM applicant %s after accept", member.id)

        async with session_scope() as session:
            result = await session.execute(select(Ticket).where(Ticket.id == ticket.id))
            db_ticket = result.scalar_one()
            db_ticket.status = "accepted_pending_close"

        await interaction.response.send_message(
            f"{member.mention} заявка принята. Канал будет закрыт через 1 час.",
        )
        channel = interaction.channel
        if isinstance(channel, discord.TextChannel):
            await channel.send(welcome, view=PostAcceptView(self.cog))
        asyncio.create_task(self.cog.schedule_close(ticket.id))

    @discord.ui.button(
        label="Отклонить заявку",
        style=discord.ButtonStyle.danger,
        custom_id="applications:reject",
    )
    async def reject(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        ticket = await self._load_ticket(interaction)
        allowed, message = await self._check_actor(interaction, ticket)
        if not allowed or ticket is None:
            await _say(interaction, message or "Недостаточно прав.")
            return
        await interaction.response.send_modal(RejectReasonModal(self.cog))


class RejectReasonModal(discord.ui.Modal):
    reason = discord.ui.TextInput(
        label="Причина отказа", style=discord.TextStyle.paragraph, max_length=1000
    )

    def __init__(self, cog: ApplicationsCog) -> None:
        super().__init__(title="Отклонение заявки")
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.channel is None:
            await _say(interaction, "Тикет не найден.")
            return

        reason_text = str(self.reason).strip()
        async with session_scope() as session:
            result = await session.execute(
                select(Ticket).where(Ticket.channel_id == interaction.channel.id)
            )
            ticket = result.scalar_one_or_none()
            if ticket is None:
                await _say(interaction, "Тикет не найден.")
                return
            ticket_id = ticket.id
            applicant_id = ticket.applicant_id
            ticket.rejection_reason = reason_text
            ticket.status = "rejected"
            ticket.closed_at = datetime.now(UTC)

        member = interaction.guild.get_member(applicant_id)
        if member is not None:
            try:
                await member.send(f"Ваша заявка была отклонена. Причина: {reason_text}")
            except discord.HTTPException:
                log.warning("cannot DM reject reason to %s", member.id)

        await interaction.response.send_message(f"Заявка отклонена. Причина: {reason_text}")
        channel = interaction.channel
        if isinstance(channel, discord.TextChannel):
            await channel.send(f"Причина отказа: {reason_text}")
        await self.cog.close_ticket(ticket_id, accepted=False)


class NicknameModal(discord.ui.Modal, title="Установить никнейм"):
    def __init__(self, cog: ApplicationsCog) -> None:
        super().__init__()
        self.cog = cog
        self.nickname = discord.ui.TextInput(
            label="Новый никнейм",
            placeholder="[Nick] | Имя",
            max_length=32,
        )
        self.add_item(self.nickname)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.channel is None:
            await _say(interaction, "Тикет не найден.")
            return
        ticket = await self.cog.get_ticket_for_channel(interaction.channel.id)
        if ticket is None:
            await _say(interaction, "Тикет не найден.")
            return
        member = interaction.guild.get_member(ticket.applicant_id)
        if member is None:
            await _say(interaction, "Заявитель не найден.")
            return
        try:
            await member.edit(
                nick=str(self.nickname).strip(),
                reason="Принятая заявка: никнейм",
            )
            await _say(interaction, "Никнейм обновлён.")
        except discord.HTTPException:
            await _say(interaction, "Не удалось обновить никнейм.")


class TicketBirthdayModal(discord.ui.Modal):
    def __init__(self, cog: ApplicationsCog) -> None:
        super().__init__(title="Указать день рождения")
        self.cog = cog
        self.birthday = discord.ui.TextInput(
            label="Дата рождения",
            placeholder="17.05 / 17 мая / may 17",
            max_length=50,
        )
        self.add_item(self.birthday)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.channel is None:
            await _say(interaction, "Тикет не найден.")
            return
        parsed = parse_date(str(self.birthday))
        if not parsed:
            await _say(interaction, "Не удалось распознать дату.")
            return
        day, month = parsed
        success = await self.cog._save_birthday(interaction.channel.id, day, month)
        if not success:
            await _say(interaction, "Тикет не найден.")
            return
        await _say(interaction, f"День рождения сохранён: {day:02d}.{month:02d}")


class PostAcceptView(discord.ui.View):
    def __init__(self, cog: ApplicationsCog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Установить никнейм",
        style=discord.ButtonStyle.primary,
        custom_id="applications:setnick",
    )
    async def set_nickname(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(NicknameModal(self.cog))

    @discord.ui.button(
        label="Указать день рождения",
        style=discord.ButtonStyle.secondary,
        custom_id="applications:setbirthday",
    )
    async def set_birthday(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(TicketBirthdayModal(self.cog))


class AddQuestionModal(discord.ui.Modal):
    def __init__(self, cog: ApplicationsCog, kind: str = APPLICATION_KIND_MAIN) -> None:
        super().__init__(title="Добавить вопрос")
        self.cog = cog
        self.kind = kind
        self.question = discord.ui.TextInput(
            label="Текст вопроса",
            style=discord.TextStyle.paragraph,
            max_length=300,
        )
        self.add_item(self.question)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with session_scope() as session:
            count_result = await session.execute(
                select(func.count(ApplicationQuestion.id)).where(
                    ApplicationQuestion.is_active.is_(True),
                    ApplicationQuestion.kind == self.kind,
                )
            )
            active_count = count_result.scalar_one()
            if active_count >= APPLICATION_MAX_QUESTIONS:
                limit = APPLICATION_MAX_QUESTIONS
                await _say(interaction, f"Нельзя добавить больше {limit} вопросов.")
                return
            max_order_result = await session.execute(
                select(func.max(ApplicationQuestion.order)).where(
                    ApplicationQuestion.kind == self.kind
                )
            )
            max_order = max_order_result.scalar_one() or 0
            session.add(
                ApplicationQuestion(
                    order=max_order + 1,
                    question=str(self.question).strip(),
                    is_active=True,
                    kind=self.kind,
                )
            )

        embed = await self.cog.render_questions_embed(self.kind)
        await interaction.response.edit_message(
            embed=embed, view=QuestionManagerView(self.cog, self.kind)
        )


class RemoveQuestionModal(discord.ui.Modal):
    def __init__(self, cog: ApplicationsCog, kind: str = APPLICATION_KIND_MAIN) -> None:
        super().__init__(title="Убрать вопрос")
        self.cog = cog
        self.kind = kind
        self.number = discord.ui.TextInput(label="Номер вопроса", max_length=10)
        self.add_item(self.number)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            number = int(str(self.number).strip())
        except ValueError:
            await _say(interaction, "Введите корректный номер вопроса.")
            return

        async with session_scope() as session:
            result = await session.execute(
                select(ApplicationQuestion)
                .where(
                    ApplicationQuestion.is_active.is_(True),
                    ApplicationQuestion.kind == self.kind,
                )
                .order_by(ApplicationQuestion.order.asc())
            )
            questions = list(result.scalars().all())
            if number < 1 or number > len(questions):
                await _say(interaction, "Вопрос с таким номером не найден.")
                return
            to_remove = questions[number - 1]
            to_remove.is_active = False
            remaining = [item for item in questions if item.id != to_remove.id]
            for index, question in enumerate(remaining, start=1):
                question.order = index

        embed = await self.cog.render_questions_embed(self.kind)
        await interaction.response.edit_message(
            embed=embed, view=QuestionManagerView(self.cog, self.kind)
        )


class QuestionManagerView(discord.ui.View):
    def __init__(self, cog: ApplicationsCog, kind: str = APPLICATION_KIND_MAIN) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.kind = kind

    @discord.ui.button(label="Добавить вопрос", style=discord.ButtonStyle.success)
    async def add_question(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(AddQuestionModal(self.cog, self.kind))

    @discord.ui.button(label="Убрать вопрос", style=discord.ButtonStyle.secondary)
    async def remove_question(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(RemoveQuestionModal(self.cog, self.kind))

    @discord.ui.button(label="Закончить", style=discord.ButtonStyle.primary)
    async def finish(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ApplicationsCog(bot))  # type: ignore[arg-type]
