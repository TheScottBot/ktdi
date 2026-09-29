"""/settings: per-server settings: shared state (see db.scope) and the Don (who /whospray asks, /tdoi obeys)."""

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import common, config, db
from ktdi.common import NO_PINGS, log

SHARED_THINGS = "quotes, sprays, bribes and campaigns"


def shared_state_text(guild: discord.Guild) -> str:
    if not db.is_shared(guild.id):
        return f"🔒 **Off**: {SHARED_THINGS} are local to this server."
    others = sum(1 for g in common.bot.guilds if g.id != guild.id and db.is_shared(g.id))
    if others == 0:
        return f"🔗 **On**, but no other server the bot is in has it on, so {SHARED_THINGS} aren't shared with anyone yet."
    servers = "1 other server that has" if others == 1 else f"{others} other servers that have"
    return f"🔗 **On**: {SHARED_THINGS} are shared with the {servers} it on."


@commands.hybrid_group(name="settings", description="This server's settings for the bot.", invoke_without_command=True)
@commands.guild_only()
async def settings_group(ctx: commands.Context):
    await settings_show.callback(ctx)


def whospray_text(guild: discord.Guild) -> str:
    user_id = db.whospray_user(guild.id)
    return f"<@{user_id}>" if user_id else "Nobody yet."


def can_choose_the_don():
    """Only the user IDs in WHOSPRAY_ADMIN_IDS (.env) may choose the Don; not even server admins otherwise."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id not in config.WHOSPRAY_ADMIN_IDS:
            raise commands.CheckFailure("Only the people listed in the bot's `WHOSPRAY_ADMIN_IDS` can choose the Don.")
        return True
    return commands.check(predicate)


@settings_group.command(name="show", description="Show this server's settings.")
async def settings_show(ctx: commands.Context):
    embed = discord.Embed(title=f"⚙️ Settings for {ctx.guild.name}", color=discord.Color.blurple())
    embed.add_field(name="Shared state", value=shared_state_text(ctx.guild), inline=False)
    embed.add_field(name="The Don (asked by /whospray, obeyed with /tdoi)", value=whospray_text(ctx.guild), inline=False)
    embed.set_footer(text="Shared state needs Manage Server to change. The Don can only be chosen by the people "
                          "listed in the bot's WHOSPRAY_ADMIN_IDS.")
    await ctx.send(embed=embed, allowed_mentions=NO_PINGS)


@settings_group.command(name="whospray_user", description="Choose the Don, who /whospray asks. Leave empty to clear it.")
@can_choose_the_don()
@app_commands.describe(user="The Don: who gets asked who should be sprayed")
async def settings_whospray_user(ctx: commands.Context, user: discord.Member | None = None):
    db.set_whospray_user(ctx.guild.id, user.id if user else None)
    log.info("[%s] %s set the Don to %s", ctx.guild.name, ctx.author, user or "nobody")
    if user:
        await ctx.send(f"🤌 {user.mention} is now the Don. `/whospray` will ask them.", allowed_mentions=NO_PINGS)
    else:
        await ctx.send("🤌 There's no Don now. `/whospray` and `/tdoi` won't work until one is chosen again.")


@settings_group.command(name="shared_state",
                        description="Share quotes, sprays, bribes and campaigns with the bot's other servers, or not.")
@commands.has_guild_permissions(manage_guild=True)
@app_commands.describe(value="True: shared with the bot's other servers. False: only this server.")
async def settings_shared_state(ctx: commands.Context, value: bool):
    if value == db.is_shared(ctx.guild.id):
        await ctx.send(f"Shared state is already {'on' if value else 'off'}.\n{shared_state_text(ctx.guild)}",
                       ephemeral=True)
        return
    db.set_shared(ctx.guild.id, value)
    log.info("[%s] %s turned shared state %s", ctx.guild.name, ctx.author, "on" if value else "off")
    if value:
        note = ("This server now sees what the other shared servers have added, and they see what this server added. "
                "If two servers have a campaign with the same alias, each server's own comes first.")
    else:
        note = ("From now on this server only sees what was added here, and the other servers stop seeing it. "
                "Nothing is deleted: turning it back on shares everything again.")
    await ctx.send(f"{shared_state_text(ctx.guild)}\n{note}")


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    parent = command.parent.name if command.parent else None
    if not (command.name == "settings" or parent == "settings"):
        return "", []
    text = (f"• **On** (the default): {SHARED_THINGS} are pooled with every other server the bot is in that has it "
            "on. Quotes, rap sheets and `/campaign list` include theirs.\n"
            f"• **Off**: {SHARED_THINGS} are local to this server, and other servers can't see them.\n"
            "• Switching is reversible: everything remembers which server it came from, so nothing is lost.\n"
            "• Books, reminders' channels and each server's roles stay per-server either way.\n"
            f"• Only people with **Manage Server** can change it: `/settings shared_state value:False`, "
            f"or `{config.COMMAND_PREFIX}settings shared_state false`.")
    don = ("• `/settings whospray_user user:@someone` chooses the Don: who `/whospray` asks, and who `/tdoi` obeys. "
           "Leave `user` empty to clear it.\n"
           "• It's per server (never shared). Only the people listed in the bot's `WHOSPRAY_ADMIN_IDS` can change "
           "it; being a server admin isn't enough.")
    return "", [("Shared state", text, False), ("The Don", don, False)]


async def setup(bot: commands.Bot):
    bot.add_command(settings_group)
