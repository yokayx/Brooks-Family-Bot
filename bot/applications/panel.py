"""Панель управления набором: эмбед со статусами составов и кнопки.

Отдельный модуль, чтобы ког заявок (bot/cogs/applications.py) занимался
тикетами, а панель жила своей жизнью: состав, его роль, статус набора,
переключатель и менеджер формы.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.applications import forms
from bot.config import (
    APPLICATION_KIND_COMPOSITIONS,
    APPLICATION_KIND_MAIN,
    APPLICATION_KIND_ROLE_IDS,
    APPLICATION_KIND_VZP,
)
from bot.roster.manager import is_leader

PANEL_TITLE = "Панель управления набором"
PANEL_COLOR = discord.Color.from_rgb(88, 101, 242)
# Порядок составов в панели и на кнопках.
PANEL_KINDS: tuple[str, ...] = (APPLICATION_KIND_MAIN, APPLICATION_KIND_VZP)


def composition_text(kind: str) -> str:
    """Название состава так же, как в меню заявок."""
    return APPLICATION_KIND_COMPOSITIONS.get(kind, forms.kind_label(kind))


def composition_role_mention(kind: str) -> str:
    """Тег роли состава: её и пингуют в меню заявок."""
    return f"<@&{APPLICATION_KIND_ROLE_IDS[kind]}>"


def build_control_panel_embed(*, main_open: bool, vzp_open: bool) -> discord.Embed:
    """Эмбед панели: по полю на состав — роль, статус набора словами."""
    states = {
        APPLICATION_KIND_MAIN: main_open,
        APPLICATION_KIND_VZP: vzp_open,
    }
    embed = discord.Embed(title=PANEL_TITLE, color=PANEL_COLOR)
    for kind in PANEL_KINDS:
        is_open = states[kind]
        embed.add_field(
            name=composition_text(kind),
            value=(
                f"{composition_role_mention(kind)}\n"
                f"{forms.status_mark(is_open)} {forms.panel_label(kind)} — "
                f"{forms.status_text(is_open).lower()}"
            ),
            inline=False,
        )
    return embed


async def _say(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.send_message(text, ephemeral=True)


class ControlPanelView(discord.ui.View):
    """Панель управления: одна кнопка на функцию, цвет — по состоянию функции."""

    def __init__(
        self,
        cog: commands.Cog,
        *,
        main_open: bool = False,
        vzp_open: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        states = {
            APPLICATION_KIND_MAIN: main_open,
            APPLICATION_KIND_VZP: vzp_open,
        }
        for kind in PANEL_KINDS:
            self._add_toggle(
                kind,
                f"Набор {forms.panel_label(kind)}",
                states[kind],
                f"control:{kind}:toggle",
                row=0,
            )
        for kind in PANEL_KINDS:
            self._add_form(kind, f"Форма {forms.panel_label(kind)}", f"control:{kind}:form", row=1)

    def _add_toggle(self, kind: str, label: str, is_open: bool, custom_id: str, row: int) -> None:
        button = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.success if is_open else discord.ButtonStyle.danger,
            custom_id=custom_id,
            row=row,
        )

        async def callback(interaction: discord.Interaction) -> None:
            await self._toggle(interaction, kind)

        button.callback = callback
        self.add_item(button)

    def _add_form(self, kind: str, label: str, custom_id: str, row: int) -> None:
        button = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=custom_id,
            row=row,
        )

        async def callback(interaction: discord.Interaction) -> None:
            await self._form(interaction, kind)

        button.callback = callback
        self.add_item(button)

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
        state = forms.status_text(not is_open).lower()
        await interaction.followup.send(
            f"Набор {forms.panel_label(kind)}: {state}.", ephemeral=True
        )

    async def _form(self, interaction: discord.Interaction, kind: str) -> None:
        if not await self._leader(interaction):
            return
        await self.cog.open_form_editor(interaction, kind)
