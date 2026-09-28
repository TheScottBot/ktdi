"""/help: the command list, and details for one command.

Features add their own detail through a help_extras(command) function (see ktdi.features), so adding a feature
never means editing this file.
"""

import importlib

import discord
from discord.ext import commands

from ktdi import config
from ktdi.common import log
from ktdi.features import FEATURES

EMBED_FIELD_LIMIT = 1024  # Discord rejects the whole message if any field is longer.
EMBED_TOTAL_LIMIT = 6000


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
    embed = discord.Embed(
        title="Keep The Degenerates Inline",
        description=f"Use `/command` or `{p}command`.",
        color=discord.Color.blurple(),
    )
    for cmd in sorted(ctx.bot.commands, key=lambda c: c.name):
        if not can_use(cmd, ctx):
            continue  # e.g. /books outside the library servers.
        usage = (" | ".join(sorted(sub.name for sub in cmd.commands if not sub.extras.get("prefix_only")))
                 if isinstance(cmd, commands.Group) else cmd.signature)
        embed.add_field(name=f"/{cmd.name} {usage}".strip(), value=cmd.description or "No description.", inline=False)
    for module in feature_modules():
        for name, value in getattr(module, "main_help_fields", lambda: [])():
            embed.add_field(name=name, value=value, inline=False)
    embed.set_footer(text="Use /help <command> for details, e.g. /help abm for every unit it understands.")
    await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    bot.add_command(help_command)
