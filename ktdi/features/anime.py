"""/anime: ask our resident anime watcher (ANIME_USER_ID in .env) what they think of a random anime."""

import random

import discord
from discord.ext import commands

from ktdi import config
from ktdi.common import log
from ktdi.lib import anilist

HELP_CATEGORY = "🎲 Fun"

ANIME_LINES = [
    "{user}, what are your thoughts on {anime}?",
    "{user}, quick one: {anime}. Good or overrated?",
    "{user}, where does {anime} rank for you?",
    "{user}, have you seen {anime}? Thoughts?",
    "{user}, sell us on {anime} in one sentence. Or warn us off it.",
    "{user}, {anime}: masterpiece, mid, or never watched?",
    "{user}, what's your hottest take on {anime}?",
    "{user}, if {anime} got a new season tomorrow, would you watch it?",
    "{user}, rate {anime} out of 10. Show your working.",
    "{user}, the people demand to know: what do you think of {anime}?",
    "{user}, would you recommend {anime} to the group?",
    "{user}, describe {anime} badly.",
]


def anime_text(anime: anilist.Anime) -> str:
    title = discord.utils.escape_markdown(anime.title)
    # Angle brackets stop Discord adding a big preview for the link.
    return f"**[{title}](<{anime.url}>)**" if anime.url else f"**{title}**"


@commands.hybrid_command(name="anime", description="Ask our resident anime watcher what they think of a random anime.")
async def anime(ctx: commands.Context):
    if not config.ANIME_USER_ID:
        await ctx.send("Nobody's set up to be asked yet. Add their user ID as `ANIME_USER_ID` in the bot's `.env`.",
                       ephemeral=True)
        return
    await ctx.defer()  # AniList can take a moment, and slash commands must answer within 3 seconds.
    picked = await anilist.random_anime()
    log.info("Asked about the anime %r", picked.title)
    line = random.choice(ANIME_LINES).format(user=f"<@{config.ANIME_USER_ID}>", anime=anime_text(picked))
    # Ping only the person being asked.
    await ctx.send(line, allowed_mentions=discord.AllowedMentions(
        users=[discord.Object(id=config.ANIME_USER_ID)], everyone=False, roles=False))


async def setup(bot: commands.Bot):
    bot.add_command(anime)
