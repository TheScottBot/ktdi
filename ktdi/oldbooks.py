"""Shared by the old-book commands (/vulgartongue, /deadword, /devils, /dream, /phrase, /beeton, /enquire, /almanac,
/melancholy, /pliny, /pseudodoxia, /bestiary, /secrets, /wonder, /goblin, /omen, /flowermeaning and the rest): a book of entries looked up by
headword, and the replies they have in common.

A command makes a Dictionary of its entries, then asks it to look things up (the headword's entry, else the entries
that use the word, else one spelt like it: fuzzy.look_up), for a random entry, or for autocomplete. How an entry looks
is the command's own business; the list of entries that use a word looks the same everywhere (uses_embed).

Every old book also declares itself as OLD_BOOK (an OldBook, or a list of them): how /lore searches it alongside the
others, how Old Wisdom of the Day gets a random entry from it, and which shelves it's on (SHELVES: /nature, /folklore,
/esoteric, /words, /household search just theirs). A new old book isn't finished without one.
"""

import importlib
import random
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, Iterable, TypeVar

import discord
from discord import app_commands

from ktdi.common import choices
from ktdi.lib import fuzzy

T = TypeVar("T")
SHOWN = 8  # Entries listed when a word turns up in several
LINE_LENGTH = 140  # Each listed entry's name and summary (not counting its link), clipped
TYPED_LENGTH = 60  # What was typed, when it's shown back
LONGEST = 1500  # An entry longer than this is cut short, with the rest a click away
MORE = "\n\n*…the rest is in the book.*"
CURATED = ("There may be more on it in the {where}: what's here was picked by hand to keep this a safe space. Or "
           "there may simply be nothing on it.")


def clip(text: str, limit: int) -> str:
    """Cut to fit at a space, with an ellipsis."""
    return text if len(text) <= limit else text[:text.rfind(" ", 0, limit - 1)].rstrip(",;:") + "…"


def fit(paragraphs: list[str], limit: int) -> str:
    """As many whole paragraphs as fit in `limit` characters (the first cut short, if even it won't), saying when
    there's more in the book."""
    text = paragraphs[0] if paragraphs else ""
    if len(text) > limit:
        return clip(text, limit) + MORE
    for paragraph in paragraphs[1:]:
        if len(text) + len(paragraph) + 2 > limit:
            return text + MORE
        text += "\n\n" + paragraph
    return text


def escape(text: str) -> str:
    """A Gutenberg book's text made safe for Discord, with its _italics_ kept as italics and its -- as dashes."""
    text = re.sub(r"\s*--\s*", "—", text)
    return re.sub(r"\\_(.+?)\\_", r"*\1*", discord.utils.escape_markdown(text))


def shown_typed(query: str) -> str:
    """What someone typed, tidied and made safe to show back."""
    return discord.utils.escape_markdown(" ".join(query.split())[:TYPED_LENGTH])


class Dictionary(Generic[T]):
    """A book's entries, looked up by any of their names (`names`: "BABE or BABY" is both), with `text` the part to
    search for a word's uses. `meaning_first`: see fuzzy.containing; `close_first`: see fuzzy.look_up. `shown_name` is
    a name as autocomplete offers it."""

    def __init__(self, entries: list[T], names: Callable[[T], Iterable[str]], text: Callable[[T], str],
                 meaning_first: bool = True, shown_name: Callable[[str], str] = str, close_first: bool = False):
        self.entries, self.text, self.meaning_first, self.close_first = entries, text, meaning_first, close_first
        self.index = fuzzy.index((entry, name) for entry in entries for name in names(entry))
        self.names = sorted({shown_name(name) for entry in entries for name in names(entry)}, key=str.casefold)
        self._by_name: dict[str, list[T]] = {}
        for entry in entries:
            for name in names(entry):
                self._by_name.setdefault(name.casefold(), []).append(entry)
        self._first_name = {id(entry): next(iter(names(entry)), "").casefold() for entry in entries}

    def look_up(self, query: str, close_first: bool | None = None) -> fuzzy.LookUp | None:
        """The entries for a headword typed exactly (even one fuzzy matching skips, like "I"), else fuzzy.look_up.
        `close_first` overrides the dictionary's own for this once (/lore wants what mentions a thing before what's
        spelt like it, even in a book whose command doesn't)."""
        exact = self._by_name.get(" ".join(query.split()).casefold())
        if exact:
            return fuzzy.LookUp("exact", exact)
        return fuzzy.look_up(query, self.index, self.entries, self.text, self.meaning_first,
                             close_first=self.close_first if close_first is None else close_first)

    def one_of(self, query: str | None) -> tuple[T, int] | None:
        """For books of passages rather than definitions (Beeton's advice, Enquire Within): one passage on what was
        typed, picked at random from all that are (see look_up), and how many others there are; or (nothing typed)
        any passage. None if nothing's about it. A passage found by a name brings the others filed under that name
        with it ("unicorns" is any of the Unicorn passages, not just the first)."""
        if not query or not fuzzy.words(query):
            return random.choice(self.entries), 0
        found = self.look_up(query)
        if not found:
            return None
        entries = found.entries
        if found.kind != "uses":
            match = fuzzy.best_match(query, self.index, spelling=fuzzy.STRICT_SPELLING)
            entries = self._by_name.get(match.name.casefold(), entries) if match else entries
        return random.choice(entries), len(entries) - 1

    def named_in(self, query: str) -> list[T]:
        """The entries for a name somewhere in what was typed, the longest name first: "I dreamt about baby carriages
        again" finds Baby Carriages, and "my teeth fell out" Teeth. A plural finds its singular ("eels": Eel)."""
        words = re.findall(r"[\w'-]+", query.casefold())
        for length in range(len(words), 0, -1):
            phrases = [" ".join(words[i:i + length]) for i in range(len(words) - length + 1)]
            for phrase in sorted(phrases, key=len, reverse=True):  # Of the same number of words, the longest
                found = self._by_name.get(phrase) or self._by_name.get(fuzzy.singular(phrase))
                if found:
                    return found
        return []

    def uses(self, query: str, leave_out: T | None = None) -> list[T]:
        """The entries whose text uses the words typed (see fuzzy.containing)."""
        return fuzzy.containing(query, [e for e in self.entries if e is not leave_out], self.text, self.meaning_first)

    def same_name(self, entry: T) -> list[T]:
        """The entry and any others filed under exactly the same name (REASON, v.i. and REASON, n.)."""
        return self._by_name.get(self._first_name.get(id(entry)), [entry])

    def autocomplete(self, current: str) -> list[app_commands.Choice[str]]:
        """Names starting with what's typed, then containing it; a random handful before anything's typed."""
        if current.strip():
            return choices(fuzzy.starting_first(current, self.names))
        return choices(random.sample(self.names, min(25, len(self.names))))


def mention(text: str, query: str) -> str:
    """Where a text mentions what was typed: from the start if it does early on, otherwise from the sentence (or
    line of verse) that does, after an ellipsis. "bright" in ABRACADABRA's long verse is "…And his eyes uncommonly
    bright."."""
    patterns = [re.compile(rf"\b{re.escape(word)}\w*", re.IGNORECASE) for word in fuzzy.words(query)]
    starts = [match.start() for pattern in patterns if (match := pattern.search(text))]
    if not starts or min(starts) < LINE_LENGTH // 2:
        return " ".join(text.split())
    at = min(starts)
    sentence = max(text.rfind(end, 0, at) + len(end) for end in (". ", "! ", "? ", "; ", "\n"))
    if at - sentence > LINE_LENGTH // 2:  # A long sentence: start a few words before the word
        sentence = text.rfind(" ", 0, at - LINE_LENGTH // 3) + 1
    return "…" + " ".join(text[sentence:].split())


def modern_spelling(text: str) -> str:
    """Old spelling made modern enough to search ("wyfe", "loue", "vnicorne", "inuisible" are "wife", "love",
    "unicorne", "invisible"): v at a word's start before a consonant is u; u between vowels, or after n, r or l
    and before a vowel and a consonant ("seruant", not "true"), is v; and y after a consonant and inside a word is
    i. Only for finding things: what's shown keeps the book's spelling."""
    text = re.sub(r"\b([Vv])(?=[^aeiouAEIOU\W])", lambda m: "U" if m[1] == "V" else "u", text)
    text = re.sub(r"(?<=[aeiouAEIOU])u(?=[aeiou])|(?<=[nrl])u(?=[aeiou][b-df-hj-np-tv-z])", "v", text)
    return re.sub(r"(?<=[b-df-hj-np-tv-zB-DF-HJ-NP-TV-Z])y(?=\w)", "i", text)


def not_here(message: str, where: str = "book itself") -> str:
    """A reply to something an old book doesn't have here, saying that this is a hand-picked selection: the book may
    say more, or nothing."""
    return f"{message}\n-# {CURATED.format(where=where)}"


def titled(passages: list[dict]) -> "Dictionary":
    """A book of titled passages ({"title", "text"}: Pliny's chapters, Browne's, Burton's), looked up by title, and
    then by what the passages say; the title counts as the passage's opening, so passages about a topic come before
    ones that only mention it."""
    return Dictionary(passages, names=lambda p: [p["title"]], text=lambda p: f"{p['title']}. {p['text']}")


def passage_embed(passage: dict, others: int, *, emoji: str, colour: discord.Color, link: str | None, footer: str,
                  more: str) -> discord.Embed:
    """A titled passage, as much as fits, with where it's from in the footer, and (if there are `others` on the same
    topic) `more`, formatted with how many in all: "He has more on that: ask again ({n} chapters)."."""
    text = fit([escape(paragraph) for paragraph in passage["text"].split("\n\n")], LONGEST)
    embed = discord.Embed(title=f"{emoji} {escape(passage['title'])}"[:256], url=link, description=text, color=colour)
    embed.set_footer(text=footer.rstrip(".") + "." + (f" {more.format(n=others + 1)}" if others else ""))
    return embed


def one_passage(book: "Dictionary", topic: str | None, show: Callable[[dict, int], discord.Embed], *, emoji: str,
                colour: discord.Color, nothing: str) -> discord.Embed:
    """A passage on the topic (or any, with none), shown by `show(passage, others)`; or `nothing`, if there's none."""
    found = book.one_of(topic)
    if not found:
        return discord.Embed(title=f"{emoji} {shown_typed(topic)}", description=not_here(nothing), color=colour)
    return show(*found)


def uses_embed(found: list[T], *, query: str, title: str, name: Callable[[T], str], text: Callable[[T], str],
               link: Callable[[T], str], source: str, colour: discord.Color) -> discord.Embed:
    """A few of the entries that use a word, one line each ("**Name**: where it's mentioned", clipped), each name
    linking to its own place in the book, with a footer saying if there are more. Names come escaped for Discord;
    `text` is an entry's own text, as the book has it."""
    shown = random.sample(found, min(SHOWN, len(found)))
    lines = [f"**[{name(e)}]({link(e)})**: "
             f"{escape(clip(mention(text(e), query), max(LINE_LENGTH - len(name(e)) - 2, 20)))}" for e in shown]
    embed = discord.Embed(title=title[:256], description="\n".join(lines)[:4096], color=colour)
    more = f". Showing {len(shown)} of {len(found)}: ask again for others." if len(found) > len(shown) else ""
    embed.set_footer(text=f"{source}{more}")
    return embed


@dataclass(frozen=True)
class Shelf:
    """A shelf of old books, between /lore (every book) and a book's own command: /esoteric salt is salt in the books
    of magic, and the magic in the others."""
    emoji: str
    name: str  # "Esoteric": the embed says "🔮 Esoteric: salt"
    short: str  # What's on it, in a few words, for its command's one-line description
    about: str  # What's on it, for its /help page
    examples: str  # What to try


SHELVES = {  # The command for each, and what's on it; every old book is on at least one (tests/test_lore.py)
    "nature": Shelf(
        "🦉", "Natural history", "Pliny, Browne, Topsell's beasts and Culpeper's plants",
        "Pliny, Browne's vulgar errors, Topsell's beasts, Culpeper's plants and the Victorian wonders",
        "dragons, elephants, the moon, eels or the mandrake"),
    "folklore": Shelf(
        "🧚", "Folklore", "goblins, superstitions, flowers and old sayings",
        "Welsh goblins, everyday superstitions, the language of flowers, the almanac, weather sayings and the "
        "Victorian wonders", "fairies, salt, Friday, roses or ghosts"),
    "esoteric": Shelf(
        "🔮", "Esoteric", "secrets, dreams, gems, talismans and charms",
        "Albertus Magnus's secrets, dreams, astrological cures, gems and talismans, magic squares, witches, and the "
        "magic in the folklore books", "salt, the moon, rubies, scarabs or eagles"),
    "words": Shelf(
        "📚", "Words", "slang, lost words, Bierce and Brewer",
        "Grose's slang, Mackay's lost words, Bierce's Devil's Dictionary and Brewer's phrases",
        "drunk, love, fool, money or the devil"),
    "household": Shelf(
        "🏠", "Household", "Mrs Beeton, Enquire Within, manners and melancholy",
        "Mrs Beeton, Enquire Within, the etiquette manuals, the 1531 herbal and Burton's melancholy",
        "eggs, servants, dinner, cheese or sleep"),
}


@dataclass(frozen=True)
class OldBook:
    """An old book as /lore and Old Wisdom of the Day see it. `random` is any entry, as its own command shows it.
    `find` (for /lore) is what it has on a topic, as Dictionary.look_up finds it; None for a book that can't be
    searched by topic (/almanac goes by date). `title`, `link` and `text` are an entry's name, its place in the book,
    and the text /lore quotes from (plain text, as the book has it: /lore escapes it). `send`, for a book whose post
    is more than an embed (/herbal's, which people dig into), posts a random one itself: send(where, content).
    `shelves` are the SHELVES it's on; `entry_shelves`, for a book with some entries that belong on another shelf
    too (/omen's charms against witches are esoteric as well as folklore), is the extra shelves an entry is on."""
    book: str  # Who wrote what: "Pliny the Elder, Natural History (AD 77)"
    emoji: str
    command: str  # The command with more: "pliny", or "beeton recipe"
    random: Callable[[], discord.Embed]
    find: Callable[[str], fuzzy.LookUp | None] | None = None
    title: Callable[[Any], str] = lambda entry: entry["title"]
    link: Callable[[Any], str | None] = lambda entry: None
    text: Callable[[Any], str] = lambda entry: entry["text"]
    send: Callable[[discord.abc.Messageable, str | None], Awaitable[discord.Message]] | None = None
    shelves: tuple[str, ...] = ()
    entry_shelves: Callable[[Any], Iterable[str]] = lambda entry: ()

    def find_on(self, shelf: str | None, topic: str) -> fuzzy.LookUp | None:
        """What it has on a topic (as `find`), on a shelf: all of it if the book's on that shelf, else only the
        entries that are on it themselves; with no shelf, all of it."""
        if not self.find:
            return None
        found = self.find(topic)
        if not found or shelf is None or shelf in self.shelves:
            return found
        entries = [entry for entry in found.entries if shelf in self.entry_shelves(entry)]
        return fuzzy.LookUp(found.kind, entries) if entries else None

    async def post(self, where: discord.abc.Messageable, content: str | None = None) -> discord.Message:
        """A random entry, posted (with `content` above it)."""
        if self.send:
            return await self.send(where, content)
        return await where.send(content, embed=self.random(), allowed_mentions=discord.AllowedMentions.none())


def every_book() -> list[OldBook]:
    """Every old book, in the order the features load, from each feature's OLD_BOOK (one, or a list)."""
    from ktdi.features import FEATURES  # Here, not at the top: the features import this module

    found = []
    for name in FEATURES:
        books = getattr(importlib.import_module(name), "OLD_BOOK", None)
        found.extend(books if isinstance(books, list) else [books] if books else [])
    return found
