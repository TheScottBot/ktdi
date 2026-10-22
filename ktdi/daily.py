"""Posting something every day in a channel each server chooses: Old Wisdom of the Day (/wisdom setup), the almanac's
day (/almanac setup) and the daily bread (/bread setup).

A feature registers a Daily (what it's called, and how to post today's), gives its command a `setup` group whose
here/stop/show subcommands call setup_here, stop and show below, and calls start() in its setup. Each server has
at most one channel and time for each Daily (setting it up elsewhere moves it), stored in the daily_posts table, so
nothing needs a restart. daily_loop checks every minute, on the minute. A post that fails because Discord couldn't
be reached (the network's down: UNREACHABLE) is tried again the next minute; any other failure (a permission, a bug)
moves it on to the next day, so nothing's tried over and over. A post can't be partly made: one that fails undoes
what it did. A day missed by hours (the bot was down, or the network was) is skipped, not posted late.
"""

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

import discord
from discord.ext import commands, tasks

from ktdi import common, config, db
from ktdi.common import NO_PINGS, log
from ktdi.lib import reminders

DEFAULT_TIME = "9am"
GRACE = timedelta(hours=6)  # Later than this, a day's is skipped rather than posted late
EVERY_DAY = tuple(range(7))
UNREACHABLE = common.UNREACHABLE  # Tried again the next minute, until GRACE runs out


@dataclass(frozen=True)
class Daily:
    """Something posted every day. `post(channel, last)` posts today's and returns what to remember for tomorrow's
    (Old Wisdom of the Day: the book it came from, so tomorrow's is from another); `note` is a line for the reply to
    `setup here`."""
    kind: str  # Its key in the database: "wisdom"
    name: str  # "Old Wisdom of the Day", as a sentence starts
    emoji: str
    command: str  # The command its setup is under: "wisdom"
    post: Callable[[discord.abc.Messageable, str | None], Awaitable[str | None]]
    note: Callable[[], str] = lambda: ""


DAILIES: dict[str, Daily] = {}


def register(daily: Daily) -> Daily:
    DAILIES[daily.kind] = daily
    return daily


# --- Where and when ---
@dataclass(frozen=True)
class Setup:
    guild_id: int
    kind: str
    channel_id: int
    clock: str  # "09:00", in BOT_TIMEZONE
    next_run: str  # UTC, ISO
    last: str | None
    set_by: int

    @property
    def next_run_at(self) -> datetime:
        return datetime.fromisoformat(self.next_run)


COLUMNS = "guild_id, kind, channel_id, clock, next_run, last, set_by"


def _setup(row: sqlite3.Row | tuple | None) -> Setup | None:
    return Setup(*row) if row else None


def get_setup(guild_id: int, kind: str) -> Setup | None:
    return _setup(db.conn.execute(f"SELECT {COLUMNS} FROM daily_posts WHERE guild_id = ? AND kind = ?",
                                  (guild_id, kind)).fetchone())


def save_setup(guild_id: int, kind: str, channel_id: int, clock: str, next_run: datetime, set_by: int) -> None:
    """Set up (or move) a server's daily post; what it remembered from the last one is kept."""
    db.conn.execute(
        "INSERT INTO daily_posts (guild_id, kind, channel_id, clock, next_run, set_by) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (guild_id, kind) DO UPDATE SET channel_id = excluded.channel_id, clock = excluded.clock, "
        "next_run = excluded.next_run, set_by = excluded.set_by",
        (guild_id, kind, channel_id, clock, next_run.isoformat(), set_by))
    db.conn.commit()


def stop_setup(guild_id: int, kind: str) -> bool:
    stopped = db.conn.execute("DELETE FROM daily_posts WHERE guild_id = ? AND kind = ?", (guild_id, kind)).rowcount > 0
    db.conn.commit()
    return stopped


def due(now: datetime) -> list[Setup]:
    rows = db.conn.execute(f"SELECT {COLUMNS} FROM daily_posts").fetchall()
    return [setup for setup in map(_setup, rows) if setup.next_run_at <= now]


def posted(setup: Setup, next_run: datetime, last: str | None) -> None:
    db.conn.execute("UPDATE daily_posts SET next_run = ?, last = COALESCE(?, last) WHERE guild_id = ? AND kind = ?",
                    (next_run.isoformat(), last, setup.guild_id, setup.kind))
    db.conn.commit()


def next_post(clock: str, after: datetime) -> datetime:
    """The next time (UTC) after `after` that it's that time of day where the bot is."""
    hour, minute = map(int, clock.split(":"))
    schedule = reminders.Schedule(EVERY_DAY, hour, minute)
    return reminders.next_occurrence(schedule, after, config.BOT_TIMEZONE).astimezone(timezone.utc)


# --- Posting ---
@tasks.loop(minutes=1)
async def daily_loop():
    now = datetime.now(timezone.utc)
    for setup in due(now):
        daily, last, again = DAILIES.get(setup.kind), None, False
        try:
            channel = common.bot.get_channel(setup.channel_id)
            if daily is None:
                pass  # A feature that's gone: it just waits
            elif channel is None:
                log.warning("%s: can't find channel %s", daily.name, setup.channel_id)
            elif now - setup.next_run_at > GRACE:
                log.warning("Skipped %s for server %s: it was due at %s", daily.name, setup.guild_id, setup.next_run)
            else:
                last = await daily.post(channel, setup.last)
                where = getattr(getattr(channel, "guild", None), "name", setup.guild_id)
                log.info("Posted %s in %s", daily.name, where)
        except UNREACHABLE as error:  # No network, or Discord's down: it'll be back, so try again in a minute
            again = True
            log.warning("Couldn't reach Discord to post %s in server %s (%s): trying again in a minute",
                        setup.kind, setup.guild_id, error or type(error).__name__)
        except discord.HTTPException as error:
            log.warning("Couldn't post %s in server %s: %s", setup.kind, setup.guild_id, error)
        except Exception:  # A bug in one post mustn't stop the loop, and every other server's posts with it
            log.exception("%s failed in server %s", setup.kind, setup.guild_id)
        finally:  # Otherwise on to tomorrow, so a failure can't post it over and over (and GRACE ends the retries)
            if not again:
                posted(setup, next_post(setup.clock, now), last)


@daily_loop.before_loop
async def before_daily_loop():
    await common.bot.wait_until_ready()
    # Start on the minute, so each check is just after one ticks over: a post due at 9:00 goes at 9:00, not at
    # whatever second past the minute the bot happened to start (up to a minute late).
    await asyncio.sleep(seconds_to_next_minute(datetime.now(timezone.utc)))


def seconds_to_next_minute(now: datetime) -> float:
    return 60 - now.second - now.microsecond / 1_000_000 + 0.5  # Half a second in, to be sure it's ticked over


def start() -> None:
    """Start the loop (once, however many features call this)."""
    if not daily_loop.is_running():
        daily_loop.start()


# --- The setup commands ---
def setup_text(daily: Daily, setup: Setup | None) -> str:
    if setup is None:
        return (f"{daily.name} isn't set up here. Someone with Manage Server can run `/{daily.command} setup here` "
                f"in the channel it should go to.")
    when = int(setup.next_run_at.timestamp())
    return (f"{daily.emoji} {daily.name} goes to <#{setup.channel_id}> every day at {setup.clock} "
            f"({config.BOT_TIMEZONE.key} time). The next is <t:{when}:R>. Set up by <@{setup.set_by}>.")


async def setup_here(ctx: commands.Context, daily: Daily, time: str | None) -> None:
    """/<command> setup here [time]: post it in this channel every day (moving it here if it was elsewhere)."""
    try:
        hour, minute = reminders.parse_clock(time or DEFAULT_TIME)
    except reminders.ScheduleError as error:
        await ctx.send(str(error), ephemeral=True)
        return
    clock = f"{hour:02d}:{minute:02d}"
    before = get_setup(ctx.guild.id, daily.kind)
    save_setup(ctx.guild.id, daily.kind, ctx.channel.id, clock, next_post(clock, datetime.now(timezone.utc)),
               ctx.author.id)
    log.info("[%s] %s set %s to %s at %s", ctx.guild.name, ctx.author, daily.name, ctx.channel, clock)
    lines = [setup_text(daily, get_setup(ctx.guild.id, daily.kind))]
    if note := daily.note():
        lines.append(f"-# {note}")
    if before and before.channel_id != ctx.channel.id:
        lines.append(f"-# It's moved here from <#{before.channel_id}>.")
    me = getattr(ctx.guild, "me", None)
    if me and not ctx.channel.permissions_for(me).send_messages:
        lines.append("⚠️ I can't post in this channel yet: give me Send Messages and Embed Links here.")
    await ctx.send("\n".join(lines), allowed_mentions=NO_PINGS)


async def stop(ctx: commands.Context, daily: Daily) -> None:
    """/<command> setup stop."""
    if stop_setup(ctx.guild.id, daily.kind):
        log.info("[%s] %s stopped %s", ctx.guild.name, ctx.author, daily.name)
        await ctx.send(f"{daily.emoji} {daily.name} won't be posted any more. `/{daily.command}` still works "
                       f"whenever you ask.")
    else:
        await ctx.send(f"{daily.name} isn't set up here, so there's nothing to stop.", ephemeral=True)


async def show(ctx: commands.Context, daily: Daily) -> None:
    """/<command> setup show."""
    await ctx.send(setup_text(daily, get_setup(ctx.guild.id, daily.kind)), ephemeral=True, allowed_mentions=NO_PINGS)
