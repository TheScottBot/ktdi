"""Small helpers shared by several features."""

import logging
from dataclasses import dataclass

import discord
from discord.ext import commands

log = logging.getLogger("ktdi")

# The running bot, for code with no ctx to hand (background loops, reaction listeners). Set by create_bot().
bot: commands.Bot | None = None

NO_PINGS = discord.AllowedMentions.none()


@dataclass
class Reply:
    content: str | None = None
    embed: discord.Embed | None = None
    private: bool = False  # Only shown to the person who asked (slash commands only).


async def send_reply(ctx: commands.Context, reply: Reply) -> None:
    await ctx.send(reply.content, embed=reply.embed, allowed_mentions=NO_PINGS)


async def respond(interaction: discord.Interaction, reply: Reply) -> None:
    await interaction.response.send_message(reply.content, embed=reply.embed, ephemeral=reply.private,
                                            allowed_mentions=NO_PINGS)


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


async def get_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
    try:
        return guild.get_member(user_id) or await guild.fetch_member(user_id)
    except discord.HTTPException:
        return None  # Left the server, or couldn't look them up.
