"""/help: the command list, and details for one command.

Features add their own detail through a help_extras(command) function and choose where their commands sit on the
main list with HELP_CATEGORY (see ktdi.features), so adding a feature never means editing this file.
"""

import importlib
import sys

import discord
from discord.ext import commands

from ktdi import config
from ktdi.common import log
from ktdi.features import FEATURES

HELP_CATEGORY = "🔧 Utilities"

EMBED_FIELD_LIMIT = 1024  # Discord rejects the whole message if any field is longer.
EMBED_TOTAL_LIMIT = 6000
EMBED_FIELD_COUNT_LIMIT = 25
# The main list's categories, in this order. A category not listed here goes after these, alphabetically.
CATEGORY_ORDER = ["💦 Rap sheet", "🎲 Fun", "🎬 Movie night", "📏 Measurements", "💬 Quotes", "🗓️ Campaigns", "🔧 Utilities"]
UNCATEGORISED = "🧩 Other"


def feature_modules():
    return [importlib.import_module(name) for name in FEATURES if name != __name__]


def can_use(command: commands.Command, ctx: commands.Context) -> bool:
    """Whether to show a command in /help here. A command can opt out with extras["available"](guild)."""
    available = (command.root_parent or command).extras.get("available")
    return available(ctx.guild) if available else True


def add_help_field(embed: discord.Embed, name: str, value: str, inline: bool = False) -> None:
    """Add a field, trimming (and logging) rather than letting an over-long one break the whole message."""
    if len(value) > EMBED_FIELD_LIMIT:
        log.warning("Help field %r is %d characters; trimmed to %d", name, len(value), EMBED_FIELD_LIMIT)
        value = value[:EMBED_FIELD_LIMIT - 1] + "…"
    embed.add_field(name=name[:256], value=value, inline=inline)


def fit_embed(embed: discord.Embed) -> discord.Embed:
    """Drop trailing fields if the whole embed is over Discord's limit."""
    while len(embed) > EMBED_TOTAL_LIMIT and embed.fields:
        log.warning("Help embed %r is %d characters; dropping field %r", embed.title, len(embed), embed.fields[-1].name)
        embed.remove_field(len(embed.fields) - 1)
    return embed


def command_help_embed(command: commands.Command) -> discord.Embed:
    """Detailed help for one command or subcommand, e.g. /help abm or /help campaign remind."""
    p = config.COMMAND_PREFIX
    embed = discord.Embed(
        title=f"/{command.qualified_name} {command.signature}".strip(),
        description=f"{command.description}\n\nAlso works as `{p}{command.qualified_name}`.",
        color=discord.Color.blurple(),
    )
    if isinstance(command, commands.Group):
        embed.title = f"/{command.name}"
        embed.description = f"{command.description}\n\nAlso works as `{p}{command.name} <subcommand>`."
    extra_fields = []
    for module in feature_modules():
        if hasattr(module, "help_extras"):
            description, fields = module.help_extras(command)
            embed.description += description
            extra_fields += fields
    if isinstance(command, commands.Group):
        for sub in sorted(command.commands, key=lambda c: c.name):
            prefix = p if sub.extras.get("prefix_only") else "/"
            add_help_field(embed, f"{prefix}{sub.qualified_name} {sub.signature}".strip(), sub.description)
    for name, value, inline in extra_fields:
        add_help_field(embed, name, value, inline)
    return fit_embed(embed)


def command_category(command: commands.Command) -> str:
    """extras["category"] if the command sets one, otherwise its feature's HELP_CATEGORY."""
    module = sys.modules.get(command.callback.__module__)
    return command.extras.get("category") or getattr(module, "HELP_CATEGORY", UNCATEGORISED)


def command_line(command: commands.Command) -> str:
    """One line on the main list, e.g. `/spray [user]`: Spray the degenerate."""
    if isinstance(command, commands.Group):
        usage = " | ".join(sorted(sub.name for sub in command.commands if not sub.extras.get("prefix_only")))
    else:
        usage = command.signature
    name = f"/{command.name} {usage}".strip()
    return f"`{name}`: {command.description or 'No description.'}"


def main_help_lines(ctx: commands.Context) -> dict[str, list[str]]:
    """The main list's lines, grouped by category and in display order."""
    lines: dict[str, list[str]] = {}
    for cmd in sorted(ctx.bot.commands, key=lambda c: c.name):
        if can_use(cmd, ctx):  # e.g. /books is left out away from the library servers.
            lines.setdefault(command_category(cmd), []).append(command_line(cmd))
    for module in feature_modules():
        for category, line in getattr(module, "main_help_lines", lambda: [])():
            lines.setdefault(category, []).append(line)

    def position(category):
        return (CATEGORY_ORDER.index(category), "") if category in CATEGORY_ORDER else (len(CATEGORY_ORDER), category)
    return {category: lines[category] for category in sorted(lines, key=position)}


def category_fields(lines: dict[str, list[str]]) -> list[tuple[str, str]]:
    """One field per category, split into "(cont.)" fields rather than going over Discord's field limit."""
    fields = []
    for category, category_lines in lines.items():
        chunk: list[str] = []
        for line in category_lines:
            if chunk and len("\n".join(chunk + [line])) > EMBED_FIELD_LIMIT:
                fields.append((category, "\n".join(chunk)))
                chunk = []
            chunk.append(line)
        if chunk:
            fields.append((category, "\n".join(chunk)))
    return [(name if i == 0 or fields[i - 1][0] != name else f"{name} (cont.)", value)
            for i, (name, value) in enumerate(fields)]


def paginate(title: str, description: str, footer: str, fields: list[tuple[str, str]]) -> list[discord.Embed]:
    """Spread fields over as many embeds as Discord's limits need; usually just one."""
    page_footer_room = len("Page 99 of 99. ")

    def new_page() -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
        embed.set_footer(text=footer)
        return embed

    pages = [new_page()]
    for name, value in fields:
        page = pages[-1]
        too_long = len(page) + len(name) + min(len(value), EMBED_FIELD_LIMIT) + page_footer_room > EMBED_TOTAL_LIMIT
        if page.fields and (len(page.fields) >= EMBED_FIELD_COUNT_LIMIT or too_long):
            page = new_page()
            pages.append(page)
        add_help_field(page, name, value)
    if len(pages) > 1:
        for number, page in enumerate(pages, 1):
            page.set_footer(text=f"Page {number} of {len(pages)}. {footer}")
    return [fit_embed(page) for page in pages]


def main_help_pages(ctx: commands.Context) -> list[discord.Embed]:
    return paginate(
        title="Keep The Degenerates Inline",
        description=f"Use `/command` or `{config.COMMAND_PREFIX}command`.",
        footer="Use /help <command> for details, e.g. /help abm for every unit it understands.",
        fields=category_fields(main_help_lines(ctx)),
    )


class HelpPages(discord.ui.View):
    """◀ / ▶ buttons for the main list, only used once it no longer fits on one page."""

    def __init__(self, pages: list[discord.Embed], author_id: int):
        super().__init__(timeout=600)
        self.pages = pages
        self.author_id = author_id
        self.page = 0
        self.message: discord.Message | None = None
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # The list is posted in the channel, so stop one person flipping it under everyone else.
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Run your own `/help` to flip through it.", ephemeral=True)
            return False
        return True

    async def _show(self, interaction: discord.Interaction) -> None:
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(self.page - 1, 0)
        await self._show(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.page + 1, len(self.pages) - 1)
        await self._show(interaction)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


@commands.hybrid_command(name="help", description="List everything this bot can do, or details for one command.")
async def help_command(ctx: commands.Context, *, command: str | None = None):
    p = config.COMMAND_PREFIX
    if command:
        found = ctx.bot.get_command(command.lstrip("/" + p).lower())
        if found is None or not can_use(found, ctx):
            await ctx.send(f"There's no `{command}` command. Try `/help` for the list.", ephemeral=True)
        else:
            # Private for /help <command>, so the details don't fill the channel.
            await ctx.send(embed=command_help_embed(found), ephemeral=True)
        return
    pages = main_help_pages(ctx)
    if len(pages) == 1:
        await ctx.send(embed=pages[0])
        return
    view = HelpPages(pages, ctx.author.id)
    view.message = await ctx.send(embed=pages[0], view=view)


async def setup(bot: commands.Bot):
    bot.add_command(help_command)
