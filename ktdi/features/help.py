"""/help: a short front page (where to start, and the sections), each section's commands, and details for one
command.

/help on its own is the front page, with a menu to open any section privately. /help <section> ("old oddities",
"rap sheet") is a section's commands; /help <command> is one command in detail. Features add their own detail through
a help_extras(command) function and choose their section with HELP_CATEGORY (see ktdi.features), so adding a feature
never means editing this file; adding a section does (CATEGORIES).
"""

import importlib
import sys

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import config
from ktdi.common import log
from ktdi.lib import fuzzy
from ktdi.features import FEATURES

HELP_CATEGORY = "🔧 Utilities"

EMBED_FIELD_LIMIT = 1024  # Discord rejects the whole message if any field is longer.
EMBED_TOTAL_LIMIT = 6000
EMBED_FIELD_COUNT_LIMIT = 25
# The sections, in this order, each with what's in it for the front page. A section a feature names that isn't here
# goes after these, alphabetically (with no description).
CATEGORIES = {
    "💦 Rap sheet": "Sprays, telling-offs, blame, bribes and the committee",
    "🎲 Fun": "Looting, Linux, anime and the war archives",
    "📚 Words & wisdom": "Old dictionaries, idioms, slang, manners and gloom",
    "🔮 Old oddities": "Dreams, almanacs, herbs, witches and Mrs Beeton",
    "🎬 Movie night": "Countdowns, bingo, votes and ratings",
    "📏 Measurements": "Units, sincerely or absurdly",
    "💬 Quotes": "Save and replay what people say",
    "🗓️ Campaigns": "Our games' links and session reminders",
    "🔧 Utilities": "Timezones, weather and settings",
}
CATEGORY_ORDER = list(CATEGORIES)
UNCATEGORISED = "🧩 Other"
START_HERE = ["spray", "rapsheet", "bad", "quote random", "nowplaying"]  # On the front page, for anyone new


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
    elif not isinstance(command, commands.HybridCommand):  # !-only (e.g. !quote anon): there's no slash version.
        embed.title = f"{p}{command.qualified_name} {command.signature}".strip()
        embed.description = f"{command.description}\n\nOnly works typed with `{p}`."
    extra_fields = []
    for module in feature_modules():
        if hasattr(module, "help_extras"):
            description, fields = module.help_extras(command)
            embed.description += description
            extra_fields += fields
    if isinstance(command, commands.Group):
        subcommands = [(sub.name, f"{p if sub.extras.get('prefix_only') else '/'}{sub.qualified_name} {sub.signature}",
                        sub.description) for sub in command.commands]
        if getattr(command, "fallback", None):  # The group itself, as a slash subcommand: /beeton recipe [dish]
            subcommands.append((command.fallback, f"/{command.name} {command.fallback} {command.signature}",
                                command.description))
        for _, usage, description in sorted(subcommands):
            add_help_field(embed, usage.strip(), description)
    for name, value, inline in extra_fields:
        add_help_field(embed, name, value, inline)
    return fit_embed(embed)


def command_category(command: commands.Command) -> str:
    """extras["category"] if the command sets one, otherwise its feature's HELP_CATEGORY."""
    module = sys.modules.get(command.callback.__module__)
    return command.extras.get("category") or getattr(module, "HELP_CATEGORY", UNCATEGORISED)


def command_line(command: commands.Command) -> str:
    """One line on a section's page: "`/spray [target]`: Spray the degenerate.", or for a command with subcommands,
    "`/quote …`: Save and replay..." (/help quote lists them)."""
    usage = "…" if isinstance(command, commands.Group) else command.signature
    return f"`{f'/{command.name} {usage}'.strip()}`: {command.description or 'No description.'}"


def main_help_lines(ctx: commands.Context) -> dict[str, list[str]]:
    """Each section's lines, in section order: its commands, then any lines features add (main_help_lines())."""
    lines: dict[str, list[str]] = {}
    for cmd in sorted(ctx.bot.commands, key=lambda c: c.name):
        # Left out: /books away from the library servers, and cryptids (extras["hidden"]), which you have to know about.
        if can_use(cmd, ctx) and not cmd.extras.get("hidden"):
            lines.setdefault(command_category(cmd), []).append(command_line(cmd))
    for module in feature_modules():
        for category, line in getattr(module, "main_help_lines", lambda: [])():
            lines.setdefault(category, []).append(line)

    def position(category):
        return (CATEGORY_ORDER.index(category), "") if category in CATEGORY_ORDER else (len(CATEGORY_ORDER), category)
    return {category: lines[category] for category in sorted(lines, key=position)}


def section_name(category: str) -> str:
    """"🔮 Old oddities" is "Old oddities"."""
    return category.split(" ", 1)[1] if " " in category else category


def start_here(ctx: commands.Context) -> list[str]:
    """START_HERE's commands that are here."""
    return [f"`/{name}`" for name in START_HERE
            if (command := ctx.bot.get_command(name)) and can_use(command, ctx)]


def front_page(ctx: commands.Context, lines: dict[str, list[str]]) -> discord.Embed:
    """What /help shows first: where to start, and the sections, a line each."""
    sections = [f"{category.split(' ', 1)[0]} **{section_name(category)}**"
                + (f": {CATEGORIES[category]}" if category in CATEGORIES else "") + f" ({len(category_lines)})"
                for category, category_lines in lines.items()]
    picks = start_here(ctx)
    description = (f"**Start here:** {' · '.join(picks)}\n\n" if picks else "") + "\n".join(sections)
    embed = discord.Embed(title="Keep The Degenerates Inline", description=description, color=discord.Color.blurple())
    embed.set_footer(text=f"Pick a section below (or /help <section>), or /help <command> for one command. Every "
                          f"command also works typed with {config.COMMAND_PREFIX}.")
    return embed


def section_page(category: str, category_lines: list[str]) -> discord.Embed:
    """A section's commands, a line each."""
    embed = discord.Embed(title=category, description=CATEGORIES.get(category, ""), color=discord.Color.blurple())
    embed.description = "\n\n".join(part for part in (embed.description, "\n".join(category_lines)) if part)[:4096]
    embed.set_footer(text="/help <command> for one in detail, and what it can do.")
    return embed


def find_section(text: str, lines: dict[str, list[str]]) -> str | None:
    """The section someone typed ("old oddities", "rapsheet", "Movie"), loosely: or None."""
    match = fuzzy.best_match(text, fuzzy.index((category, section_name(category)) for category in lines),
                             spelling=fuzzy.STRICT_SPELLING)
    return match.thing if match else None


class HelpMenu(discord.ui.View):
    """The front page's menu of sections. Whoever picks one sees it privately, so anyone can use the menu."""

    def __init__(self, lines: dict[str, list[str]]):
        super().__init__(timeout=600)
        self.lines = lines
        self.message: discord.Message | None = None
        self.sections.options = [
            discord.SelectOption(label=section_name(category)[:100], value=category[:100],
                                 emoji=category.split(" ", 1)[0] if " " in category else None,
                                 description=CATEGORIES.get(category, "")[:100] or None)
            for category in list(lines)[:25]]

    @discord.ui.select(placeholder="Pick a section…")
    async def sections(self, interaction: discord.Interaction, select: discord.ui.Select):
        category = select.values[0]
        await interaction.response.send_message(embed=section_page(category, self.lines.get(category, [])),
                                                ephemeral=True)

    async def on_timeout(self) -> None:
        # The menu stops working after 10 minutes, so grey it out.
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


@commands.hybrid_command(name="help", description="Where to start, the sections, or details for one command.")
@app_commands.describe(command="A command (spray, quote add) or a section (old oddities, rap sheet). Empty: the list")
async def help_command(ctx: commands.Context, *, command: str | None = None):
    lines = main_help_lines(ctx)
    if command:
        found = ctx.bot.get_command(command.lstrip("/" + config.COMMAND_PREFIX).lower())
        if found is not None and can_use(found, ctx):
            # Private, so the details don't fill the channel.
            await ctx.send(embed=command_help_embed(found), ephemeral=True)
        elif section := find_section(command, lines):
            await ctx.send(embed=section_page(section, lines[section]), ephemeral=True)
        else:
            await ctx.send(f"There's no `{command}` command or section. Try `/help` for the list.", ephemeral=True)
        return
    view = HelpMenu(lines)
    view.message = await ctx.send(embed=front_page(ctx, lines), view=view)


async def setup(bot: commands.Bot):
    bot.add_command(help_command)
