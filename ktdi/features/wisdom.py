"""/wisdom: Old Wisdom, a random entry from any of the old books (each feature's OLD_BOOK: see ktdi.oldbooks), and
Old Wisdom of the Day, the same posted every day in a channel a server chooses (ktdi/daily.py).

/wisdom (typed: !wisdom) posts one where it's asked for. /wisdom setup here [time] (Manage Server) makes the channel
it's run in the server's Old Wisdom of the Day channel, posting at that time each day (BOT_TIMEZONE, 9am unless
told otherwise); /wisdom setup stop stops it, and /wisdom setup show says where and when. Each day's comes from a
different book to the day before: a book is picked first, then an entry from it, so the books with thousands of
entries (Grose, Miller) don't drown out the small ones. A new old book takes part as soon as it has an OLD_BOOK.
"""

import random

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import daily, oldbooks

HELP_CATEGORY = "📚 Words & wisdom"

old_books = oldbooks.every_book


def pick(last: str | None = None) -> oldbooks.OldBook:
    """Any old book, but not the one it came from last time (unless it's the only one)."""
    books = old_books()
    return random.choice([book for book in books if book.command != last] or books)


async def post_wisdom(where: discord.abc.Messageable, heading: str, last: str | None = None) -> str:
    """One, from any book but `last`; returns the book's command (the daily post remembers it)."""
    book = pick(last)
    await book.post(where, f"{heading}, from `/{book.command}`")
    return book.command


DAILY = daily.register(daily.Daily(
    "wisdom", "Old Wisdom of the Day", "📜", "wisdom",
    post=lambda channel, last: post_wisdom(channel, "📜 **Old Wisdom of the Day**", last),
    note=lambda: f"It comes from {len(old_books())} old books, a different one each day."))


@commands.hybrid_group(name="wisdom", fallback="now", invoke_without_command=True,
                       description="Old wisdom from any of the old books, at random. Or set up a daily one.")
async def wisdom_group(ctx: commands.Context):
    """A random piece of old wisdom from any of the old books: Pliny, Topsell's bestiary, the Book of Secrets,
    Mrs Beeton, the Devil's Dictionary, Grose's slang, Miller's dreams and the rest (each book's command is as likely
    as any other, however big the book). Every one comes with the command that has more from the same book.

    **Old Wisdom of the Day:** someone with Manage Server runs `/wisdom setup here` in a channel, and one is posted
    there every day, from a different book each day. Give a time (`/wisdom setup here 7:30am`) or it's 9am, where
    the bot is. `/wisdom setup show` says where and when; `/wisdom setup stop` stops it. One channel per server: set
    it up somewhere else and it moves."""
    await post_wisdom(ctx, "📜 **Old wisdom**")


@wisdom_group.group(name="setup", invoke_without_command=True,
                    description="Old Wisdom of the Day: one posted in a channel every day.")
@commands.guild_only()
async def wisdom_setup(ctx: commands.Context):
    await daily.show(ctx, DAILY)


@wisdom_setup.command(name="here", description="Post Old Wisdom of the Day in this channel, every day.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
@app_commands.describe(time="What time each day (9am, 0730, 18:30). Empty: 9am")
async def wisdom_setup_here(ctx: commands.Context, *, time: str | None = None):
    await daily.setup_here(ctx, DAILY, time)


@wisdom_setup.command(name="stop", description="Stop posting Old Wisdom of the Day.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def wisdom_setup_stop(ctx: commands.Context):
    await daily.stop(ctx, DAILY)


@wisdom_setup.command(name="show", description="Where and when Old Wisdom of the Day is posted.")
@commands.guild_only()
async def wisdom_setup_show(ctx: commands.Context):
    await daily.show(ctx, DAILY)


async def setup(bot: commands.Bot):
    bot.add_command(wisdom_group)
    daily.start()
