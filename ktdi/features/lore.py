"""/lore <thing>: what every old book has to say about something, side by side: /lore dragon is Pliny's, Browne's,
Topsell's and Albertus's dragons, Miller's dream of one, Brewer's idioms with one in, and so on.

It asks every old book that can be searched by topic (each feature's OLD_BOOK: see ktdi.oldbooks.OldBook), and shows
one entry from each that has something, with where it mentions the thing and a link to the book, then how to ask
that book for the rest. Books with an entry for the thing itself come first, then ones that mention it. A book that
only has something spelt like it is only asked about when none has the thing itself (a typo: "dragn").

The shelves (/nature, /folklore, /esoteric, /words, /household: ktdi.oldbooks.SHELVES) are the same search, only in the
books on that shelf, and the entries of other books that are on it themselves (/omen's charms against witches are on
the esoteric shelf too). A shelf's book: option asks one of its books instead, with that book's entries autocompleted
(Discord passes the book picked to the autocomplete): it runs the book's own command, so /esoteric book:talisman
thing:scarab is !talisman scarab. That's how most books are asked, with no slash command of their own
(OldBook.own_command), which keeps Discord's command list short. Typed, the book is the first word: !esoteric talisman
scarab. On its own, a shelf is a random entry from any of its books.
"""

import random

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.common import choices
from ktdi.lib import fuzzy

HELP_CATEGORY = "📚 Words & wisdom"
COLOUR = discord.Color.from_rgb(120, 94, 60)  # Parchment
SNIPPET = 200  # How much of each book's entry is quoted, when there's room
SHORTEST = 60  # ...and when there isn't, when many books have something
EMBED_LIMIT = 6000  # Discord's, for a whole embed
NOTHING = oldbooks.not_here("None of the old books has anything on that here. Try dragons, love, eels, the moon, "
                            "cheese, or the plague.", where="books themselves")


old_books = oldbooks.every_book


def searched(thing: str, shelf: str | None = None) -> list[tuple[oldbooks.OldBook, list]]:
    """The books (on the shelf, if there is one) that have something on the thing, and what: those with an entry for
    it first, then those that mention it; a near spelling only if no book has the thing itself."""
    found = [(book, hits) for book in old_books() if (hits := book.find_on(shelf, thing))]
    found = [(book, hits) for book, hits in found if hits.kind != "close"] or found
    found.sort(key=lambda pair: pair[1].kind != "exact")
    return [(book, hits.entries) for book, hits in found]


def entry_line(book: oldbooks.OldBook, entries: list, thing: str, room: int = 1024, shelf: str | None = None) -> str:
    """One entry, as a field's value: its name (linking to it), where it mentions the thing, and how to ask for the
    rest (on `shelf`, for a book asked through it); in `room` characters at most, the quote shortened to fit (but
    never below SHORTEST)."""
    entry = random.choice(entries)
    name, link = oldbooks.escape(book.title(entry)), book.link(entry)
    head = f"**[{name}]({link})**: " if link else f"**{name}**: "
    tail = ""
    if len(entries) > 1:
        asked = " ".join(thing.replace("`", "").split())[:oldbooks.TYPED_LENGTH]
        tail = f"\n-# …and {len(entries) - 1} more: `{book.asked(asked, shelf)}`"
    quote = max(SHORTEST, min(SNIPPET, room - len(head) - len(tail)))
    return (head + oldbooks.escape(oldbooks.clip(oldbooks.mention(book.text(entry), thing), quote)) + tail)[:1024]


def nothing(shelf: str | None) -> str:
    """What to say when no book (on the shelf) has anything."""
    if shelf is None:
        return NOTHING
    on = oldbooks.SHELVES[shelf]
    return oldbooks.not_here(f"Nothing on that on the {on.name.lower()} shelf. Try {on.examples}, or `/lore` for "
                             f"every book.", where="books themselves")


def lore_embed(thing: str, shelf: str | None = None) -> discord.Embed:
    """What every old book (or every one on the shelf) has to say about the thing."""
    shown = oldbooks.shown_typed(thing)
    on = oldbooks.SHELVES[shelf] if shelf else None
    title = (f"{on.emoji} {on.name}: {shown}" if on else f"📜 Lore: {shown}")[:256]
    found = searched(thing, shelf)
    if not found:
        return discord.Embed(title=title, description=nothing(shelf), color=COLOUR)
    where = f" on the {on.name.lower()} shelf" if on else ""
    embed = discord.Embed(title=title, color=COLOUR,
                          description=f"What {len(found)} old book{'s' if len(found) > 1 else ''}{where} "
                                      f"{'have' if len(found) > 1 else 'has'} to say about it.")
    embed.set_footer(text="Ask any of them for more: each says how" +
                          (", or every book with /lore." if on else ", or one shelf: " +
                           ", ".join(f"/{name}" for name in oldbooks.SHELVES) + "."))
    shown_books = found[:25]  # Discord's most fields
    share = (EMBED_LIMIT - len(embed) - 50) // len(shown_books)  # Every book gets its line: the more, the shorter
    for book, entries in shown_books:
        name = f"{book.emoji} {book.book}"[:256]
        embed.add_field(name=name, value=entry_line(book, entries, thing, share - len(name), shelf), inline=False)
        if len(embed) > EMBED_LIMIT:  # Only if even the shortest quotes don't fit
            embed.remove_field(-1)
            break
    return embed


@commands.hybrid_command(name="lore", aliases=["oldbooks"],
                         description="What every old book says about something, side by side (dragons, love, eels).")
@app_commands.describe(thing="Anything at all (dragon, love, eels, the moon, cheese...)")
async def lore(ctx: commands.Context, *, thing: str):
    """What all the old books have to say about something, side by side: `/lore dragon` is Pliny's, Browne's and
    Topsell's dragons, the Book of Secrets' dragon stone, Miller's dream of one, and whatever else turns up. One entry
    from each book, with where it mentions the thing and a link to the page; each ends with the command that has the
    rest (`/pliny dragon`, `/esoteric book:talisman thing:dragon`). Books with an entry for the thing come first, then
    ones that only mention it. Old spelling is found too ("love" finds "loue"). The almanac, the weather sayings and a
    few others go by date or chance, not topic, so they're not in it; they turn up in Old Wisdom of the Day. For one
    kind of book only, or one book, ask a shelf: `/nature`, `/folklore`, `/esoteric`, `/words` or `/household`."""
    await ctx.send(embed=lore_embed(thing))


def on_shelf(shelf: str, books: list[oldbooks.OldBook] | None = None) -> list[oldbooks.OldBook]:
    """The books on a shelf (not counting other books' entries that are on it too)."""
    return [book for book in (old_books() if books is None else books) if shelf in book.shelves]


def askable(shelf: str, books: list[oldbooks.OldBook] | None = None) -> list[oldbooks.OldBook]:
    """The books on a shelf that can be picked as its book: (the ones that can be searched by topic), the ones asked
    only here first, then the ones with commands of their own."""
    return sorted((book for book in on_shelf(shelf, books) if book.find), key=lambda book: book.own_command)


def book_choice(book: oldbooks.OldBook) -> app_commands.Choice[str]:
    """A book, as the shelf's book: menu shows it: "🧿 talisman: W. T. and K. Pavitt, The Book of Talismans…"."""
    return app_commands.Choice(name=oldbooks.clip(f"{book.emoji} {book.command}: {book.book}", 100),
                               value=book.command)


def typed_book(bot: commands.Bot, books: list[oldbooks.OldBook], typed: str) -> tuple[oldbooks.OldBook | None, str]:
    """For a shelf typed with !: the book named first, by its command or any of the command's other names (!esoteric
    talisman scarab, !esoteric amulet scarab), and what's asked of it; or no book, and everything typed."""
    named = []  # (the words naming a book, the book)
    for book in books:
        root, *rest = book.command.split()  # "beeton advice": an alias goes in place of "beeton"
        command = bot.get_command(root) if bot else None
        roots = [root, *(command.aliases if command else [])]
        named += [([name, *rest], book) for name in roots]
        if rest and bot and bot.get_command(book.command) is None:  # "beeton recipe" is just /beeton, typed
            named += [([name], book) for name in roots]
    words = [word.casefold() for word in typed.split()]
    for name, book in sorted(named, key=lambda pair: len(pair[0]), reverse=True):  # "beeton advice" before "beeton"
        if words[:len(name)] == [word.casefold() for word in name]:
            return book, " ".join(typed.split()[len(name):])
    return None, typed


def suggestions(shelf: str, book: str | None, typed: str,
                books: list[oldbooks.OldBook] | None = None) -> list[app_commands.Choice[str]]:
    """What a shelf's thing: suggests: the picked book's entries (Discord says which book's been picked), or (none
    picked) every book's on the shelf (of `books`: every old book, unless told); starting with what's typed, then
    containing it, or a random handful."""
    names = list(dict.fromkeys(name for old_book in askable(shelf, books) if not book or old_book.command == book
                               for name in old_book.names()))
    if typed.strip():
        return choices(fuzzy.starting_first(typed, names))
    return choices(random.sample(names, min(25, len(names))))


async def ask_book(ctx: commands.Context, book: oldbooks.OldBook, thing: str | None) -> None:
    """A book picked on a shelf: its own command, as if asked directly (/esoteric book:talisman thing:scarab is
    !talisman scarab), or (nothing asked) a random entry from it."""
    command = ctx.bot.get_command(book.command) or ctx.bot.get_command(book.command.split()[0])  # /beeton recipe
    if not thing or command is None:
        await book.post(ctx)
        return
    asked = next(iter(command.clean_params))  # Every book's command takes what's asked as its one option
    await command.callback(ctx, **{asked: thing})


def shelf_command(name: str, books: list[oldbooks.OldBook]) -> commands.HybridCommand:
    """/nature, /folklore and the rest: /lore on one shelf, or one of its books (`books`: every old book, for the
    menu; what it searches is whatever's there when it's asked)."""
    shelf = oldbooks.SHELVES[name]
    menu = [book_choice(book) for book in askable(name, books)][:25]  # Discord's most choices
    example = next((book for book in askable(name, books) if not book.own_command), None)

    async def command(ctx: commands.Context, book: str | None = None, *, thing: str | None = None):
        here = askable(name)
        if ctx.interaction is not None:  # /: the book is from the menu
            chosen = next((b for b in here if b.command == book), None)
        else:  # !: the book is the first word or two, if they're one
            chosen, thing = typed_book(ctx.bot, here, " ".join(part for part in (book, thing) if part))
        thing = thing.strip() if thing and thing.strip() else None
        if chosen:
            await ask_book(ctx, chosen, thing)
        elif thing:
            await ctx.send(embed=lore_embed(thing, name))
        elif books_here := on_shelf(name):
            pick = random.choice(books_here)
            await pick.post(ctx, f"{shelf.emoji} From the {shelf.name.lower()} shelf: `{pick.asked(shelf=name)}`")
        else:
            await ctx.send(nothing(name))

    picked = f"`/{name} book:{example.command}`" if example else f"`/{name} book:…`"
    command.__doc__ = (f"The {shelf.name.lower()} shelf: {shelf.about}. Pick a `book:` to ask just that one "
                       f"({picked}), with its entries suggested as you type, or leave it empty to search every book "
                       f"on the shelf at once, side by side: one entry from each, with a link to the page. Try "
                       f"{shelf.examples}. Nothing at all: a random entry from any of them. Typed, the book goes "
                       f"first if there is one: `!{name} {example.command if example else 'book'} …` or "
                       f"`!{name} …`. `/lore` asks every book.")

    async def thing_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return suggestions(name, getattr(interaction.namespace, "book", None), current)

    command = app_commands.describe(book="One of the shelf's books. Empty: every book on it",
                                    thing=f"Anything at all ({shelf.examples}). Empty: a random one")(command)
    command = app_commands.choices(book=menu)(command)
    command = commands.hybrid_command(name=name, description=f"{shelf.short[0].upper()}{shelf.short[1:]}: one book, "
                                                             f"or all of them at once.",
                                      extras={"category": shelf.category})(command)
    command.autocomplete("thing")(thing_autocomplete)
    return command


def shelf_commands() -> list[commands.HybridCommand]:
    """Every shelf's command, with every old book there is in its menu."""
    books = old_books()
    return [shelf_command(name, books) for name in oldbooks.SHELVES]


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    """A shelf's /help page lists its books."""
    if command.parent or command.name not in oldbooks.SHELVES:
        return "", []
    lines = [f"`book:{book.command}` {book.emoji} {book.book}" + ("" if not book.own_command else
                                                                  f" (also `/{book.command.split()[0]}`)")
             for book in askable(command.name)]
    others = [f"`/{book.command}`" for book in on_shelf(command.name) if not book.find]
    if others:
        lines.append(f"Also on it, by their own commands: {', '.join(others)}.")
    return "", [("📚 Its books", "\n".join(lines), False)]


async def setup(bot: commands.Bot):
    bot.add_command(lore)
    for command in shelf_commands():
        bot.add_command(command)
