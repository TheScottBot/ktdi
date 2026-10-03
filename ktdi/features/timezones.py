"""/timezone: convert a time between timezones, and remember each person's own so they can leave it out.

Someone's timezone is about them, not a server, so it's stored once per person (user_timezones has no guild_id)
and follows them everywhere. Nobody's timezone is stored unless they set it themselves.
"""

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import config, db
from ktdi.common import NO_PINGS, log
from ktdi.lib import timezones
from ktdi.lib.timezones import TimezoneError

HELP_CATEGORY = "🔧 Utilities"


def now() -> datetime:
    return datetime.now(timezone.utc)


def get_user_zone(user_id: int):
    row = db.conn.execute("SELECT zone FROM user_timezones WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    try:
        return timezones.parse_zone(row[0])
    except TimezoneError:
        return None  # The zone database dropped it; as good as unset.


def set_user_zone(user_id: int, zone) -> None:
    if zone is None:
        db.conn.execute("DELETE FROM user_timezones WHERE user_id = ?", (user_id,))
    else:
        db.conn.execute("INSERT INTO user_timezones (user_id, zone) VALUES (?, ?)"
                        " ON CONFLICT (user_id) DO UPDATE SET zone = excluded.zone", (user_id, timezones.zone_id(zone)))
    db.conn.commit()


def clock_text(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def local_time_text(zone, at: datetime) -> str:
    here = at.astimezone(zone)
    return f"**{clock_text(here)}** on {here.strftime('%a %d %b')}, {timezones.describe_zone(zone, at)}"


@commands.hybrid_group(name="timezone", aliases=["tz"], description="Convert times between timezones.",
                       invoke_without_command=True)
async def timezone_group(ctx: commands.Context):
    await timezone_show.callback(ctx)


def default_zone(user_id: int):
    """A zone left out means yours (from /timezone set), or else the bot's own (BOT_TIMEZONE)."""
    return get_user_zone(user_id) or config.BOT_TIMEZONE


@timezone_group.command(name="convert", description="Convert a time between timezones. Leave bits out for now/yours.",
                        usage="[time] [from] [to]")
@app_commands.rename(from_zone="from", to_zone="to")
@app_commands.describe(time="e.g. 7pm or 19:00 (leave empty for now)",
                       from_zone="Where that time is: a city, EST, UTC+2... (leave empty for yours)",
                       to_zone="Where to convert it to (leave empty for yours)")
async def timezone_convert(ctx: commands.Context, time: str | None = None, from_zone: str | None = None, *,
                           to_zone: str | None = None):
    if not from_zone and not to_zone:
        await ctx.send("Convert between where? Give at least a `from` or a `to`; whichever you leave out is your "
                       "timezone (`/timezone set`). E.g. `/timezone convert to:Tokyo` for the time there now.",
                       ephemeral=True)
        return
    try:
        clock = timezones.parse_clock(time) if time else None  # Left out: now.
        source = timezones.parse_zone(from_zone) if from_zone else default_zone(ctx.author.id)
        target = timezones.parse_zone(to_zone) if to_zone else default_zone(ctx.author.id)
    except TimezoneError as error:
        await ctx.send(str(error), ephemeral=True)
        return
    if timezones.zone_id(source) == timezones.zone_id(target):
        await ctx.send(f"That's {timezones.describe_zone(source, now())} at both ends: the one you left out is "
                       "your timezone. Give the other one too.", ephemeral=True)
        return
    moment = now()
    start, end = timezones.convert(clock, source, target, moment)
    there = f"**{clock_text(end)}**{timezones.day_note(start, end)} in {timezones.describe_zone(target, end)}"
    if clock is None:
        text = f"🕐 It's **{clock_text(start)}** in {timezones.describe_zone(source, start)}, so {there}."
    else:
        text = f"🕐 **{clock_text(start)}** in {timezones.describe_zone(source, start)} is {there}."
    # Discord shows this in each reader's own time, whatever timezone they're in.
    text += f"\n-# That's <t:{int(start.timestamp())}:t> where you are."
    await ctx.send(text)


@timezone_group.command(name="set", description="Set your timezone, so /timezone convert can leave out `to`.")
@app_commands.describe(zone="A city (London, New York), an abbreviation (EST, BST) or an offset (UTC+2)")
async def timezone_set(ctx: commands.Context, *, zone: str):
    try:
        parsed = timezones.parse_zone(zone)
    except TimezoneError as error:
        await ctx.send(str(error), ephemeral=True)
        return
    set_user_zone(ctx.author.id, parsed)
    log.info("%s set their timezone", ctx.author)  # Not which one: that's theirs to share.
    await ctx.send(f"🕐 Got it. It's {local_time_text(parsed, now())} for you.\n"
                   "-# `/timezone convert` uses it when you leave out `to`. `/timezone clear` forgets it.",
                   ephemeral=True)


@timezone_group.command(name="show", description="What time it is for you, or for someone else who's set theirs.")
@app_commands.describe(user="Whose time to show (leave empty for yours)")
async def timezone_show(ctx: commands.Context, user: discord.User | None = None):
    user = user or ctx.author
    zone = get_user_zone(user.id)
    if zone is None:
        if user == ctx.author:
            await ctx.send("You haven't set a timezone. `/timezone set London` (or wherever you are).", ephemeral=True)
        else:
            await ctx.send(f"{user.display_name} hasn't set a timezone.", ephemeral=True)
        return
    await ctx.send(f"🕐 It's {local_time_text(zone, now())} for {user.mention}.", allowed_mentions=NO_PINGS)


@timezone_group.command(name="clear", description="Forget your timezone.")
async def timezone_clear(ctx: commands.Context):
    set_user_zone(ctx.author.id, None)
    await ctx.send("🕐 Forgotten. Set it again any time with `/timezone set`.", ephemeral=True)


async def zone_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=label[:100], value=value) for label, value in timezones.suggestions(current)]


for _command, _param in ((timezone_convert, "from_zone"), (timezone_convert, "to_zone"), (timezone_set, "zone")):
    _command.autocomplete(_param)(zone_autocomplete)


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    if (command.root_parent or command).name != "timezone":
        return "", []
    p = config.COMMAND_PREFIX
    text = ("• Timezones can be a city (`London`, `New York`, `Tokyo`), an abbreviation (`EST`, `BST`, `CET`), an "
            "offset (`UTC+5:30`) or a full name (`America/New_York`). Abbreviations mean that place's local time, "
            "so `EST` in summer is New York summer time; the answer always says which (EDT).\n"
            "• Times: `7pm`, `19:00`, `1930`, `noon`. A time means today where it's from; leave it out for now.\n"
            "• Every part of `convert` is optional, but give at least a `from` or a `to`. Whichever zone you leave "
            "out is yours (`/timezone set`, once), or the bot's own if you haven't set one. So "
            "`/timezone convert to:Tokyo` is the time in Tokyo now, and `/timezone convert time:8pm from:EST` is "
            "8pm New York time in yours.\n"
            "• `/timezone show @someone` shows their time, if they've set theirs. Nobody's timezone is saved "
            "unless they set it.\n"
            f"• Typed with `{p}` (or `{p}tz`), put zones with spaces in quotes: "
            f"`{p}tz convert 7pm \"New York\" London`. In that form they go in order (time, from, to), so "
            f"use `now` to skip the time: `{p}tz convert now Tokyo`.")
    return "", [("How it works", text, False)]


async def setup(bot: commands.Bot):
    bot.add_command(timezone_group)
