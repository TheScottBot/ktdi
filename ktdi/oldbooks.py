"""Shared by the 📜 Old books commands (/vulgartongue, /deadword, /devils, /dream, /phrase, /beeton, /enquire,
/almanac, /melancholy, /pliny, /pseudodoxia): a book of entries looked up by headword, and the replies they have in common.

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
LINE_LENGTH = 140  # Each listed entry's name and summary (not counting its link), clipped
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

    def look_up(self, query: str) -> fuzzy.LookUp | None:
        """The entries for a headword typed exactly (even one fuzzy matching skips, like "I"), else fuzzy.look_up."""
        exact = self._by_name.get(" ".join(query.split()).casefold())
        if exact:
            return fuzzy.LookUp("exact", exact)
        return fuzzy.look_up(query, self.index, self.entries, self.text, self.meaning_first,
                             close_first=self.close_first)

    def one_of(self, query: str | None) -> tuple[T, int] | None:
        """For books of passages rather than definitions (Beeton's advice, Enquire Within): one passage on what was
        typed, picked at random from all that are (see look_up), and how many others there are; or (nothing typed)
        any passage. None if nothing's about it."""
        if not query or not fuzzy.words(query):
            return random.choice(self.entries), 0
        found = self.look_up(query)
        return (random.choice(found.entries), len(found.entries) - 1) if found else None

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
        return discord.Embed(title=f"{emoji} {shown_typed(topic)}", description=nothing, color=colour)
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
