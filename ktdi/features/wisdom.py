"""/wisdom: Old Wisdom, a random entry from any of the old books (each feature's OLD_BOOK: see ktdi.oldbooks), and
Old Wisdom of the Day, the same posted every day in a channel a server chooses.

/wisdom (typed: !wisdom) posts one where it's asked for. /wisdom setup here [time] (Manage Server) makes the channel
it's run in the server's Old Wisdom of the Day channel, posting at that time each day (BOT_TIMEZONE, 9am unless
told otherwise); /wisdom setup stop stops it, and /wisdom setup show says where and when. Each day's comes from a
different book to the day before: a book is picked first, then an entry from it, so the books with thousands of
entries (Grose, Miller) don't drown out the small ones. A new old book takes part as soon as it has an OLD_BOOK.
"""

import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ktdi import common, config, db, oldbooks
from ktdi.common import NO_PINGS, log
from ktdi.lib import reminders

HELP_CATEGORY = "🔮 Old oddities"
DEFAULT_TIME = "9am"
GRACE = timedelta(hours=6)  # Later than this (the bot was down), a day's is skipped rather than posted late
EVERY_DAY = tuple(range(7))

old_books = oldbooks.every_book


@dataclass(frozen=True)
class Setup:
    guild_id: int
    channel_id: int
    clock: str  # "09:00"
    next_run: str  # UTC, ISO
    last_book: str | None
    set_by: int

    @property
    def next_run_at(self) -> datetime:
        return datetime.fromisoformat(self.next_run)


def _setup(row: sqlite3.Row | tuple | None) -> Setup | None:
    return Setup(*row) if row else None


COLUMNS = "guild_id, channel_id, clock, next_run, last_book, set_by"


def get_setup(guild_id: int) -> Setup | None:
    return _setup(db.conn.execute(f"SELECT {COLUMNS} FROM wisdom_channels WHERE guild_id = ?", (guild_id,)).fetchone())


def save_setup(guild_id: int, channel_id: int, clock: str, next_run: datetime, set_by: int) -> None:
    db.conn.execute("INSERT OR REPLACE INTO wisdom_channels (guild_id, channel_id, clock, next_run, last_book, set_by) "
                    "VALUES (?, ?, ?, ?, (SELECT last_book FROM wisdom_channels WHERE guild_id = ?), ?)",
                    (guild_id, channel_id, clock, next_run.isoformat(), guild_id, set_by))
    db.conn.commit()


def stop_setup(guild_id: int) -> bool:
    stopped = db.conn.execute("DELETE FROM wisdom_channels WHERE guild_id = ?", (guild_id,)).rowcount > 0
    db.conn.commit()
    return stopped


def due(now: datetime) -> list[Setup]:
    rows = db.conn.execute(f"SELECT {COLUMNS} FROM wisdom_channels").fetchall()
    return [setup for setup in map(_setup, rows) if setup.next_run_at <= now]


def posted(guild_id: int, next_run: datetime, book: str | None) -> None:
    db.conn.execute("UPDATE wisdom_channels SET next_run = ?, last_book = COALESCE(?, last_book) WHERE guild_id = ?",
                    (next_run.isoformat(), book, guild_id))
    db.conn.commit()


def next_post(clock: str, after: datetime) -> datetime:
    """The next time (UTC) after `after` that it's that time of day where the bot is."""
    hour, minute = map(int, clock.split(":"))
    schedule = reminders.Schedule(EVERY_DAY, hour, minute)
    return reminders.next_occurrence(schedule, after, config.BOT_TIMEZONE).astimezone(timezone.utc)


def pick(last: str | None = None) -> oldbooks.OldBook:
    """Any old book, but not the one it came from last time (unless it's the only one)."""
    books = old_books()
    return random.choice([book for book in books if book.command != last] or books)


async def post_wisdom(where: discord.abc.Messageable, heading: str, last: str | None = None) -> oldbooks.OldBook:
    book = pick(last)
    await book.post(where, f"{heading}, from `/{book.command}`")
    return book


# --- The daily post ---
@tasks.loop(minutes=1)
async def wisdom_loop():
    now = datetime.now(timezone.utc)
    for setup in due(now):
        book = None
        try:
            channel = common.bot.get_channel(setup.channel_id)
            if channel is None:
                log.warning("Old Wisdom of the Day: can't find channel %s", setup.channel_id)
            elif now - setup.next_run_at > GRACE:
                log.warning("Skipped Old Wisdom of the Day for server %s: it was due at %s", setup.guild_id,
                            setup.next_run)
            else:
                book = await post_wisdom(channel, "📜 **Old Wisdom of the Day**", setup.last_book)
                log.info("Posted Old Wisdom of the Day in server %s, from /%s", setup.guild_id, book.command)
        except discord.HTTPException as error:
            log.warning("Couldn't post Old Wisdom of the Day in server %s: %s", setup.guild_id, error)
        finally:  # Always on to tomorrow, so a failure can't post it over and over
            posted(setup.guild_id, next_post(setup.clock, now), book.command if book else None)


@wisdom_loop.before_loop
async def before_wisdom_loop():
    await common.bot.wait_until_ready()


# --- Commands ---
def setup_text(setup: Setup | None) -> str:
    if setup is None:
        return "Old Wisdom of the Day isn't set up here. Someone with Manage Server can run `/wisdom setup here` in " \
               "the channel it should go to."
    when = int(setup.next_run_at.timestamp())
    return (f"📜 Old Wisdom of the Day goes to <#{setup.channel_id}> every day at {setup.clock} "
            f"({config.BOT_TIMEZONE.key} time). The next is <t:{when}:R>. Set up by <@{setup.set_by}>.")


@commands.hybrid_group(name="wisdom", fallback="now", invoke_without_command=True,
                       description="Old wisdom from any of the old books, at random. Or set up a daily one.")
async def wisdom_group(ctx: commands.Context):
    """A random piece of old wisdom from any of the old books: Pliny, Topsell's bestiary, the Book of Secrets,
    Mrs Beeton, the Devil's Dictionary, Grose's slang, Miller's dreams and the rest (each book is as likely as any
    other, however big it is). Every one comes with the command that has more from the same book.

    **Old Wisdom of the Day:** someone with Manage Server runs `/wisdom setup here` in a channel, and one is posted
    there every day, from a different book each day. Give a time (`/wisdom setup here 7:30am`) or it's 9am, where
    the bot is. `/wisdom setup show` says where and when; `/wisdom setup stop` stops it. One channel per server: set
    it up somewhere else and it moves."""
    await post_wisdom(ctx, "📜 **Old wisdom**")


@wisdom_group.group(name="setup", invoke_without_command=True,
                    description="Old Wisdom of the Day: one posted in a channel every day.")
@commands.guild_only()
async def wisdom_setup(ctx: commands.Context):
    await wisdom_setup_show.callback(ctx)


@wisdom_setup.command(name="here", description="Post Old Wisdom of the Day in this channel, every day.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
@app_commands.describe(time="What time each day (9am, 0730, 18:30). Empty: 9am")
async def wisdom_setup_here(ctx: commands.Context, *, time: str | None = None):
    try:
        hour, minute = reminders.parse_clock(time or DEFAULT_TIME)
    except reminders.ScheduleError as error:
        await ctx.send(str(error), ephemeral=True)
        return
    clock = f"{hour:02d}:{minute:02d}"
    moved = get_setup(ctx.guild.id)
    save_setup(ctx.guild.id, ctx.channel.id, clock, next_post(clock, datetime.now(timezone.utc)), ctx.author.id)
    log.info("[%s] %s set Old Wisdom of the Day to %s at %s", ctx.guild.name, ctx.author, ctx.channel, clock)
    note = f"\n-# It's moved here from <#{moved.channel_id}>." if moved and moved.channel_id != ctx.channel.id else ""
    me = getattr(ctx.guild, "me", None)
    if me and not ctx.channel.permissions_for(me).send_messages:
        note += "\n⚠️ I can't post in this channel yet: give me Send Messages and Embed Links here."
    await ctx.send(f"{setup_text(get_setup(ctx.guild.id))}\n-# It comes from {len(old_books())} old books, a "
                   f"different one each day.{note}", allowed_mentions=NO_PINGS)


@wisdom_setup.command(name="stop", description="Stop posting Old Wisdom of the Day.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def wisdom_setup_stop(ctx: commands.Context):
    if stop_setup(ctx.guild.id):
        log.info("[%s] %s stopped Old Wisdom of the Day", ctx.guild.name, ctx.author)
        await ctx.send("📜 No more Old Wisdom of the Day. `/wisdom` still gives one whenever you ask.")
    else:
        await ctx.send("Old Wisdom of the Day isn't set up here, so there's nothing to stop.", ephemeral=True)


@wisdom_setup.command(name="show", description="Where and when Old Wisdom of the Day is posted.")
@commands.guild_only()
async def wisdom_setup_show(ctx: commands.Context):
    await ctx.send(setup_text(get_setup(ctx.guild.id)), ephemeral=True, allowed_mentions=NO_PINGS)


async def setup(bot: commands.Bot):
    bot.add_command(wisdom_group)
    wisdom_loop.start()
