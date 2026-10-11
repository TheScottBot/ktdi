"""/weather [place]: today's real forecast (Open-Meteo, ktdi/lib/openmeteo.py) next to what 19th-century folk wisdom
has to say about it, from Richard Inwards' Weather Lore (1893, public domain), and the committee's view on who's right.

The sayings are hand-picked and tidied from the archive.org scan into ktdi/lib/weather_lore.json, each tagged with the
weather it's about and any months or day it belongs to. The saying shown is one for today's date if there is one (St
Swithin's on 15 July), else one about today's weather this time of year, else one for the month. /weather in [place] is
for anywhere (no place: WEATHER_PLACE from .env). /weather here <place> posts someone's own weather as "X checked the
weather where they are" without naming it. Where someone is is never stored: not in the database, not in memory (the
lookup skips the place cache), not in the log (/weather is never logged), and a typed !weather here is deleted. If
Open-Meteo is down, folk wisdom carries on alone.
"""

import json
import random
from datetime import date, datetime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import config
from ktdi.lib import openmeteo

HELP_CATEGORY = "🔧 Utilities"
DATA = Path(__file__).resolve().parent.parent / "lib" / "weather_lore.json"
LORE_SOURCE = "Inwards' Weather Lore (1893)"
LORE_URL = "https://archive.org/details/cu31924002969099"
WET = {"rain", "snow", "hail", "thunder", "storm"}
FAIR = {"clear", "dry"}

LORE: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))

AGREE = [
    "Folk wisdom and the forecast agree. The committee is unsettled by this.",
    "For once, science and the proverb are on the same page.",
    "The committee notes that the old ways and the new ways concur. Dress accordingly.",
]
DISAGREE = [
    "Science and folk wisdom disagree. The committee has money on the proverb.",
    "One of them is wrong. The committee sides with whichever's funnier.",
    "The forecast says one thing, the 1890s another. Bring a coat either way.",
    "They can't both be right. The committee will be consulting a cat.",
]
UNSURE = [
    "The committee is unsure how this helps, but here it is.",
    "Make of that what you will.",
    "The committee declines to comment.",
]


def now() -> datetime:
    return datetime.now(config.BOT_TIMEZONE)


def pick_saying(kinds: set[str], today: date) -> dict:
    """One for today's date if there is one, else about today's weather (and right for the month), else the month's."""
    day = today.strftime("%m-%d")
    on_the_day = [s for s in LORE if s.get("date") == day]
    about_today = [s for s in LORE if set(s["weather"]) & kinds and (not s["months"] or today.month in s["months"])]
    this_month = [s for s in LORE if today.month in s["months"]]
    return random.choice(on_the_day or about_today or this_month or LORE)


def verdict(saying: dict, kinds: set[str]) -> str:
    """Whether the saying and the forecast agree: same kind of weather, or opposite (wet against fair)."""
    said = set(saying["weather"])
    if said & kinds:
        return random.choice(AGREE)
    if (said & WET and kinds & FAIR and not kinds & WET) or (said & FAIR and kinds & WET):
        return random.choice(DISAGREE)
    return random.choice(UNSURE)


def temperature(celsius: float) -> str:
    return f"{round(celsius)}°C ({round(celsius * 9 / 5 + 32)}°F)"


def forecast_lines(forecast: openmeteo.Forecast) -> str:
    now_text, now_emoji = openmeteo.describe(forecast.now_code)
    day_text, day_emoji = openmeteo.describe(forecast.code)
    today = f"{day_emoji} Today: {day_text}, {temperature(forecast.low_c)} to {temperature(forecast.high_c)}"
    if forecast.rain_chance is not None:
        today += f", {forecast.rain_chance}% chance of rain"
    today += f", wind up to {round(forecast.wind_mph)} mph"
    return f"{now_emoji} Now: {temperature(forecast.now_c)}, {now_text}\n{today}"


def saying_text(saying: dict) -> str:
    text = "\n".join(f"> {discord.utils.escape_markdown(line.strip())}" for line in saying["text"].split(" / "))
    source = f" ({discord.utils.escape_markdown(saying['source'])})" if saying.get("source") else ""
    return f"{text}\n-# Folk wisdom{source}"


def weather_embed(forecast: openmeteo.Forecast | None, title: str, today: date) -> discord.Embed:
    kinds = forecast.kinds if forecast else set()
    saying = pick_saying(kinds, today)
    embed = discord.Embed(title=f"🌦️ {title}"[:256], color=discord.Color.blue())
    if forecast:
        embed.description = forecast_lines(forecast)
        embed.add_field(name="Meanwhile, in 1893", value=saying_text(saying)[:1024], inline=False)
        embed.add_field(name="The committee's view", value=verdict(saying, kinds), inline=False)
    else:
        embed.description = "The forecast's down. Folk wisdom will have to do."
        embed.add_field(name="In 1893", value=saying_text(saying)[:1024], inline=False)
    embed.set_footer(text=f"Forecast: Open-Meteo · Lore: {LORE_SOURCE}")
    return embed


# --- /weather ---
# /weather in [place] (typed: !weather [place]) and /weather here <place>.
# "private": the bot never logs /weather (see bot.is_private_command), so nobody's place ends up in the log file.
@commands.hybrid_group(name="weather", fallback="in", invoke_without_command=True, extras={"private": True},
                       description="Today's forecast, and what 1890s folk wisdom makes of it.")
@app_commands.describe(place="A town or city (add a county if there are several: Highbridge, Cumbria). Empty: home")
async def weather_group(ctx: commands.Context, *, place: str | None = None):
    name = " ".join((place or config.WEATHER_PLACE).split())[:100]
    await ctx.defer()  # Open-Meteo can take a moment, and slash commands must answer within 3 seconds.
    found = await openmeteo.geocode(name)
    if found is None and place and await openmeteo.geocode(config.WEATHER_PLACE) is not None:
        # Open-Meteo's up (it found home), so it's the place that's wrong.
        await ctx.send(f"I can't find “{discord.utils.escape_markdown(name)}” on the map. Try a town or city, or "
                       "add the county: `Highbridge, Somerset`.")
        return
    forecast = await openmeteo.forecast(found) if found else None
    await ctx.send(embed=weather_embed(forecast, found.name if found else name, now().date()))


@weather_group.command(name="here", description="Your weather, posted without saying where you are.")
@app_commands.describe(place="Where you are. Never shown, saved or logged")
async def weather_here(ctx: commands.Context, *, place: str):
    if ctx.interaction:
        await ctx.defer()
    else:  # Typed with !, the place is in their message for everyone to see: take it down first.
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            await ctx.send("I couldn't delete your message (I need Manage Messages), so where you are is showing. "
                           "Delete it yourself, and use `/weather here` next time.")
    # Looked up and forgotten: not cached, not stored, not logged.
    found = await openmeteo.geocode(" ".join(place.split())[:100], remember=False)
    if found is None:
        await ctx.send("I couldn't find that on the map. Try a town or city, or add the county: "
                       "`Highbridge, Somerset`.", ephemeral=True)
        return
    forecast = await openmeteo.forecast(found)
    # Never the place's name: just that it's theirs.
    title = f"{ctx.author.display_name} checked the weather where they are"
    await ctx.send(embed=weather_embed(forecast, title, now().date()))


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    if (command.root_parent or command).name != "weather":
        return "", []
    text = ("• Today's forecast (from Open-Meteo), next to a saying from Inwards' *Weather Lore* (1893): one for "
            "today's date if there is one, otherwise one about today's weather at this time of year.\n"
            f"• `/weather in <place>` for anywhere; with no place, the bot's home ({config.WEATHER_PLACE}).\n"
            "• `/weather here <place>` posts your weather as \"X checked the weather where they are\": the place "
            "is never shown, saved or logged.")
    return "", [("How it works", text, False)]


async def setup(bot: commands.Bot):
    bot.add_command(weather_group)
