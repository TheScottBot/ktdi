"""/almanac day [date] (typed: !almanac [date]): the day as William Hone's Every-Day Book (1826-27, public domain) has it: its saints, its flower,
London's mean temperature for it (1797-1816), and a passage on its customs, folklore or history.

No date: today (in BOT_TIMEZONE). A date: "5 november", "nov 5", "5/11", "tomorrow". Ask again for another passage.
/almanac setup here [time] posts the day's in a channel every morning (ktdi/daily.py, as Old Wisdom of the Day does).
The data is ktdi/lib/almanac.json, built by ktdi/tools/almanac_build.py from passages picked by hand.

The plant of the day comes with a picture of it: a botanical plate or drawing, never a photo (mostly old and coloured;
public domain or freely licensed), linked from Wikimedia Commons or the Biodiversity Heritage Library (not kept here)
and credited in the footer.
Which plate goes with which plant was decided by looking at every one, and is recorded in ktdi/lib/almanac_plates.json
by Hone's Latin name (null: looked, and there wasn't a good one; better none than the wrong plant). The candidates come
from ktdi/tools/almanac_plates_find.py, which also checks the links still work (--check). A plant with no good plate
of its own shows a relative's, from its genus as Hone named it, and says so in the footer (relative()): a picture is
half the point of the morning post, and the obscure starworts and goldenrods come in runs.
"""

import json
import random
import re
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

PLATES_DATA = DATA.with_name("almanac_plates.json")

DAYS: dict[str, dict] = json.loads(DATA.read_text(encoding="utf-8"))["days"]
PLATES: dict[str, dict | None] = json.loads(PLATES_DATA.read_text(encoding="utf-8"))["plates"]


def plate(flower: dict | None) -> dict | None:
    """The picture of the day's plant, if there's a good one: {"image", "page", "credit"}. It's found by the plant's
    Latin name as Hone gives it ("Early Witlow grass. _Draba verna._" is "Draba verna")."""
    latin = latin_name(flower)
    return (PLATES.get(latin) or relative(latin)) if latin else None


def latin_name(flower: dict | None) -> str | None:
    names = re.findall(r"_([^_]+)_", flower["plant"]) if flower else []
    return names[-1].strip(" .") if names else None


NO_RELATIVES = {"agaricus", "boletus"}  # Hone's fungi genera held mushrooms that look nothing alike


def relative(latin: str) -> dict | None:
    """No good plate of the plant itself: one of another plant of its genus as Hone named it (another starwort,
    another goldenrod), marked as a relative ("related" is its name now), so a run of obscure starworts still has
    pictures without passing one off as the other. When there are several, the plateless days of that genus take
    turns, in the order they come in the year, so a run of them doesn't show the same one."""
    genus = latin.split()[0].casefold()
    if genus in NO_RELATIVES:
        return None
    kin, images = [], set()
    for name, picture in sorted(PLATES.items()):
        if picture and name.split()[0].casefold() == genus and picture["image"] not in images:
            kin.append(picture)
            images.add(picture["image"])
    if not kin:
        return None
    plateless = list(dict.fromkeys(
        name for _, day in sorted(DAYS.items()) if (name := latin_name(day["flower"]))
        and name.split()[0].casefold() == genus and not PLATES.get(name)))
    turn = plateless.index(latin) if latin in plateless else 0
    picture = kin[turn % len(kin)]
    return {**picture, "related": picture["name"]}


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
    footer = f"{SOURCE}. Ask again for another ({count} for this day)." if count > 1 else SOURCE
    picture = plate(entry["flower"])
    if picture:
        embed.set_image(url=picture["image"])
        which = f" of a relative, {picture['related']} (we found no good one of this plant)" \
            if picture.get("related") else ""
        footer = f"{footer.rstrip('.')}. Plate{which}: {picture['credit']}."
    embed.set_footer(text=footer)
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
                       description="Today (or any day) in Hone's Every-Day Book (1826-27): saints, flower, folklore.")
@app_commands.describe(date="A day (5 november, nov 5, 5/11, tomorrow). Empty: today")
async def almanac(ctx: commands.Context, *, date: str | None = None):
    """Today, or any day (`/almanac day 5 november`, `nov 5`, `25/12`, `tomorrow`; typed, just `!almanac 5 november`),
    as William Hone's Every-Day Book (1826-27) has it: the day's saints, a passage on its customs, folklore or history,
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
