"""/lore <thing>: what every old book has to say about something, side by side: /lore dragon is Pliny's, Browne's,
Topsell's and Albertus's dragons, Miller's dream of one, Brewer's idioms with one in, and so on.

It asks every old book that can be searched by topic (each feature's OLD_BOOK: see ktdi.oldbooks.OldBook), and shows
one entry from each that has something, with where it mentions the thing and a link to the book, then how to ask
that book for the rest. Books with an entry for the thing itself come first, then ones that mention it. A book that
only has something spelt like it is only asked about when none has the thing itself (a typo: "dragn").
"""

import random

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks

HELP_CATEGORY = "📚 Words & wisdom"
COLOUR = discord.Color.from_rgb(120, 94, 60)  # Parchment
SNIPPET = 200  # How much of each book's entry is quoted, when there's room
SHORTEST = 60  # ...and when there isn't, when many books have something
EMBED_LIMIT = 6000  # Discord's, for a whole embed
NOTHING = oldbooks.not_here("None of the old books has anything on that here. Try dragons, love, eels, the moon, "
                            "cheese, or the plague.", where="books themselves")


old_books = oldbooks.every_book


def searched(thing: str) -> list[tuple[oldbooks.OldBook, list]]:
    """The books that have something on the thing, and what: those with an entry for it first, then those that
    mention it; a near spelling only if no book has the thing itself."""
    found = [(book, hits) for book in old_books() if book.find and (hits := book.find(thing))]
    found = [(book, hits) for book, hits in found if hits.kind != "close"] or found
    found.sort(key=lambda pair: pair[1].kind != "exact")
    return [(book, hits.entries) for book, hits in found]


def entry_line(book: oldbooks.OldBook, entries: list, thing: str, room: int = 1024) -> str:
    """One entry, as a field's value: its name (linking to it), where it mentions the thing, and how to ask for the
    rest; in `room` characters at most, the quote shortened to fit (but never below SHORTEST)."""
    entry = random.choice(entries)
    name, link = oldbooks.escape(book.title(entry)), book.link(entry)
    head = f"**[{name}]({link})**: " if link else f"**{name}**: "
    tail = ""
    if len(entries) > 1:
        asked = " ".join(thing.replace("`", "").split())[:oldbooks.TYPED_LENGTH]
        tail = f"\n-# …and {len(entries) - 1} more: `/{book.command} {asked}`"
    quote = max(SHORTEST, min(SNIPPET, room - len(head) - len(tail)))
    return (head + oldbooks.escape(oldbooks.clip(oldbooks.mention(book.text(entry), thing), quote)) + tail)[:1024]


def lore_embed(thing: str) -> discord.Embed:
    shown = oldbooks.shown_typed(thing)
    found = searched(thing)
    if not found:
        return discord.Embed(title=f"📜 Lore: {shown}"[:256], description=NOTHING, color=COLOUR)
    embed = discord.Embed(title=f"📜 Lore: {shown}"[:256], color=COLOUR,
                          description=f"What {len(found)} old book{'s' if len(found) > 1 else ''} "
                                      f"{'have' if len(found) > 1 else 'has'} to say about it.")
    embed.set_footer(text="Ask any of them for more with its own command.")
    shown_books = found[:25]  # Discord's most fields
    share = (EMBED_LIMIT - len(embed) - 50) // len(shown_books)  # Every book gets its line: the more, the shorter
    for book, entries in shown_books:
        name = f"{book.emoji} {book.book}"[:256]
        embed.add_field(name=name, value=entry_line(book, entries, thing, share - len(name)), inline=False)
        if len(embed) > EMBED_LIMIT:  # Only if even the shortest quotes don't fit
            embed.remove_field(-1)
            break
    return embed


@commands.hybrid_command(name="lore", aliases=["oldbooks"],
                         description="What every old book says about something, side by side (dragons, love, eels).")
@app_commands.describe(thing="Anything at all (dragon, love, eels, the moon, cheese...)")
async def lore(ctx: commands.Context, *, thing: str):
    """What all the old books have to say about something, side by side: `/lore dragon` is Pliny's, Browne's and
    Topsell's dragons, Albertus's dragon stone, Miller's dream of one, and whatever else turns up. One entry from each
    book, with where it mentions the thing and a link to the page; each ends with the command that has the rest
    (`/pliny dragon`). Books with an entry for the thing come first, then ones that only mention it. Old spelling is
    found too ("love" finds "loue"). The almanac, the weather sayings and a few others go by date or chance, not
    topic, so they're not in it; they turn up in Old Wisdom of the Day."""
    await ctx.send(embed=lore_embed(thing))


async def setup(bot: commands.Bot):
    bot.add_command(lore)
