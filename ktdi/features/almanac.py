"""/almanac day [date] (typed: !almanac [date]): the day as William Hone's Every-Day Book (1826-27, public domain) has it: its saints, its flower,
London's mean temperature for it (1797-1816), and a passage on its customs, folklore or history ("On the first of
April, 1810, Napoleon married Maria Louisa... some of the waggish Parisians called him un poisson d'Avril").

No date: today (in BOT_TIMEZONE). A date: "5 november", "nov 5", "5/11", "tomorrow". Ask again for another passage.
/almanac setup here [time] posts the day's in a channel every morning (ktdi/daily.py, as Old Wisdom of the Day does).
The data is ktdi/lib/almanac.json, built by ktdi/tools/almanac_build.py from passages picked by hand.
"""

import json
import random
from datetime import date
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import daily, oldbooks
from ktdi.common import today
from ktdi.lib import links
from ktdi.lib.reminders import ScheduleError, parse_day
from ktdi.tools.almanac_build import VOLUMES

HELP_CATEGORY = "🌿 Hearth & herbs"
DATA = Path(__file__).resolve().parent.parent / "lib" / "almanac.json"
SOURCE = "Hone's Every-Day Book (1826-27)"
COLOUR = discord.Color.dark_green()
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]

DAYS: dict[str, dict] = json.loads(DATA.read_text(encoding="utf-8"))["days"]


def heading(month: int, day: int) -> str:
    """"Saturday 11 October" (this year's), or just "29 February" when this year hasn't one."""
    try:
        weekday = f"{date(today().year, month, day):%A} "
    except ValueError:
        weekday = ""
    return f"{weekday}{day} {MONTHS[month - 1]}"


def fahrenheit_and_celsius(degrees_f: float) -> str:
    return f"{degrees_f:.1f}°F ({(degrees_f - 32) * 5 / 9:.1f}°C)"


def url(passage: dict) -> str:
    """The volume the passage is in, scrolled to it."""
    return links.gutenberg(VOLUMES[passage["volume"]], passage["text"])


def day_embed(month: int, day: int) -> discord.Embed:
    key = f"{month:02d}-{day:02d}"
    entry = DAYS.get(key)
    title = f"📅 {heading(month, day)}"
    if not entry:  # 29 February: neither 1825 nor 1826 had one
        return discord.Embed(title=title, color=COLOUR,
                             description="Hone skipped this one: neither 1825 nor 1826 had a 29th of February. "
                                         "The committee recommends treating it as a bonus day.")
    if entry["name"]:
        title += f": {entry['name']}"
    lines = []
    if entry["saints"]:
        lines.append(f"⛪ {oldbooks.escape(oldbooks.clip(entry['saints'], 300))}")
    passage = random.choice(entry["passages"]) if entry["passages"] else None
    if passage:
        lines.append(oldbooks.fit([oldbooks.escape(passage["text"])], oldbooks.LONGEST))
    if entry["flower"]:
        devoted = f" (for {oldbooks.escape(entry['flower']['for'])})" if entry["flower"]["for"] else ""
        lines.append(f"🌼 Flower of the day: {oldbooks.escape(entry['flower']['plant'])}{devoted}")
    if entry["temperature"]:
        lines.append(f"🌡️ London's average for the day, 1797–1816: {fahrenheit_and_celsius(entry['temperature'])}")
    embed = discord.Embed(title=title[:256], url=url(passage) if passage else None,
                          description="\n\n".join(lines)[:4096], color=COLOUR)
    count = len(entry["passages"])
    embed.set_footer(text=f"{SOURCE}. Ask again for another ({count} for this day)." if count > 1 else SOURCE)
    return embed


def almanac_embed(when: str | None) -> discord.Embed:
    """The day asked for, or today."""
    now = today()
    if not when or not when.strip():
        return day_embed(now.month, now.day)
    try:
        month, day = parse_day(when, now)
    except ScheduleError as error:
        return discord.Embed(title="📅 Which day?", description=str(error), color=COLOUR)
    return day_embed(month, day)


async def post_today(channel: discord.abc.Messageable, last: str | None = None) -> None:
    """The day's almanac, as posted every day."""
    await channel.send("📅 **Today in the almanac**", embed=almanac_embed(None))


DAILY = daily.register(daily.Daily("almanac", "The almanac", "📅", "almanac", post=post_today))


@commands.hybrid_group(name="almanac", aliases=["onthisday", "hone"], fallback="day", invoke_without_command=True,
                       description="Today (or any day) in Hone's Every-Day Book (1826): saints, flower, folklore.")
@app_commands.describe(date="A day (5 november, nov 5, 5/11, tomorrow). Empty: today")
async def almanac(ctx: commands.Context, *, date: str | None = None):
    """Today, or any day (`/almanac day 5 november`, `nov 5`, `25/12`, `tomorrow`; typed, just `!almanac 5 november`),
    as William Hone's Every-Day Book (1826) has it: the day's saints, a passage on its customs, folklore or history,
    its flower, and London's average temperature for it in 1797-1816. Ask again for another passage: most days have
    two or three. 29 February has nothing (neither 1825 nor 1826 had one).

    **Every morning:** someone with Manage Server runs `/almanac setup here` in a channel, and the day's almanac is
    posted there every day at 9am where the bot is, or the time given (`/almanac setup here 7am`). `/almanac setup
    show` says where and when; `/almanac setup stop` stops it. One channel per server: set it up somewhere else and
    it moves."""
    await ctx.send(embed=almanac_embed(date))


@almanac.group(name="setup", invoke_without_command=True, description="Post the day's almanac in a channel every day.")
@commands.guild_only()
async def almanac_setup(ctx: commands.Context):
    await daily.show(ctx, DAILY)


@almanac_setup.command(name="here", description="Post the day's almanac in this channel, every day.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
@app_commands.describe(time="What time each day (9am, 0730, 18:30). Empty: 9am")
async def almanac_setup_here(ctx: commands.Context, *, time: str | None = None):
    await daily.setup_here(ctx, DAILY, time)


@almanac_setup.command(name="stop", description="Stop posting the day's almanac.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def almanac_setup_stop(ctx: commands.Context):
    await daily.stop(ctx, DAILY)


@almanac_setup.command(name="show", description="Where and when the day's almanac is posted.")
@commands.guild_only()
async def almanac_setup_show(ctx: commands.Context):
    await daily.show(ctx, DAILY)


OLD_BOOK = oldbooks.OldBook(SOURCE, "📅", "almanac", random=lambda: almanac_embed(None),
                            shelves=("folklore",))  # Today's: by date, not topic



async def setup(bot: commands.Bot):
    bot.add_command(almanac)
    daily.start()
