"""Shared by the 📜 Old books dictionary commands (/vulgartongue, /deadword, /devilsdictionary, /dream): a book of
entries looked up by headword, and the replies they have in common.

A command makes a Dictionary of its entries, then asks it to look things up (the headword's entry, else the entries
that use the word, else one spelt like it: fuzzy.look_up), for a random entry, or for autocomplete. How an entry looks
is the command's own business; the list of entries that use a word looks the same everywhere (uses_embed).
"""

import random
import re
from typing import Callable, Generic, Iterable, TypeVar

import discord
from discord import app_commands

from ktdi.common import choices
from ktdi.lib import fuzzy

T = TypeVar("T")
SHOWN = 8  # Entries listed when a word turns up in several
LINE_LENGTH = 140  # Each listed entry, clipped
TYPED_LENGTH = 60  # What was typed, when it's shown back
LONGEST = 1500  # An entry longer than this is cut short, with the rest a click away
MORE = "\n\n*…the rest is in the book.*"


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


def shown_typed(query: str) -> str:
    """What someone typed, tidied and made safe to show back."""
    return discord.utils.escape_markdown(" ".join(query.split())[:TYPED_LENGTH])


class Dictionary(Generic[T]):
    """A book's entries, looked up by any of their names (`names`: "BABE or BABY" is both), with `text` the part to
    search for a word's uses. `meaning_first`: see fuzzy.containing. `shown_name` is a name as autocomplete offers it."""

    def __init__(self, entries: list[T], names: Callable[[T], Iterable[str]], text: Callable[[T], str],
                 meaning_first: bool = True, shown_name: Callable[[str], str] = str):
        self.entries, self.text, self.meaning_first = entries, text, meaning_first
        self.index = fuzzy.index((entry, name) for entry in entries for name in names(entry))
        self.names = sorted({shown_name(name) for entry in entries for name in names(entry)}, key=str.casefold)
        self._by_name: dict[str, list[T]] = {}
        for entry in entries:
            for name in names(entry):
                self._by_name.setdefault(name.casefold(), []).append(entry)
        self._first_name = {id(entry): next(iter(names(entry)), "").casefold() for entry in entries}

    def look_up(self, query: str) -> fuzzy.LookUp | None:
        """The entries for a headword typed exactly (even one fuzzy matching skips, like "I"), else fuzzy.look_up."""
        exact = self._by_name.get(" ".join(query.split()).casefold())
        if exact:
            return fuzzy.LookUp("exact", exact)
        return fuzzy.look_up(query, self.index, self.entries, self.text, self.meaning_first)

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


def uses_embed(found: list[T], *, title: str, line: Callable[[T], str], source: str, url: str | None,
               colour: discord.Color) -> discord.Embed:
    """A few of the entries that use a word, one line each, with a footer saying if there are more."""
    shown = random.sample(found, min(SHOWN, len(found)))
    embed = discord.Embed(title=title[:256], url=url, description="\n".join(clip(line(e), LINE_LENGTH) for e in shown),
                          color=colour)
    more = f". Showing {len(shown)} of {len(found)}: ask again for others." if len(found) > len(shown) else ""
    embed.set_footer(text=f"{source}{more}")
    return embed
