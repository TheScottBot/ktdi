"""/devils [word]: Ambrose Bierce's definition of it, from The Devil's Dictionary (1911, public domain).

Bierce (of Carcosa fame) defines everyday words as a cynic would: "BORE, n. A person who talks when you wish him to
listen." The entries are in ktdi/lib/devils.json, built by ktdi/tools/devils_build.py, which keeps only the entries
on a hand-read allowlist. /devils on its own is a random entry; /devils <word> looks one up (any
word order, small typos), or failing that finds the entries that use the word ("money" gets every definition that
mentions it). Each links to its place in the book.
"""

import json
import random
import re
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "📜 Old books"
DATA = Path(__file__).resolve().parent.parent / "lib" / "devils.json"
SOURCE = "Ambrose Bierce, The Devil's Dictionary (1911)"
BOOK = 972  # Project Gutenberg
ATTRIBUTION = 60  # A line this short after a verse is who "wrote" it (usually one of Bierce's made-up poets)
COLOUR = discord.Color.dark_red()

ENTRIES: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["entries"]


def names(word: str) -> list[str]:
    """Every name an entry goes by: "BABE or BABY" is BABE and BABY; "TZETZE (or TSETSE) FLY" is both flies."""
    if match := re.fullmatch(r"(.*?)\s*\(or (\w+)\)\s*(.*)", word):
        before, other, after = match.groups()
        return [f"{before} {after}".strip(), f"{other} {after}".strip()]
    return [name.strip() for name in re.split(r", | or ", word) if name.strip()]


def dictionary(entries: list[dict]) -> oldbooks.Dictionary:
    return oldbooks.Dictionary(entries, names=lambda entry: names(entry["word"]), text=lambda entry: entry["text"])


DICTIONARY = dictionary(ENTRIES)


escape = oldbooks.escape


def url(entry: dict) -> str:
    """The book, scrolled to the entry: its heading ("BORE, n.") and first few words (the first paragraph only, which
    is all one block on the page)."""
    return links.gutenberg(BOOK, f"{entry['head']} {entry['text'].split(chr(10) * 2)[0]}", least=2)


def paragraphs(entry: dict) -> list[str]:
    """The entry's paragraphs as Discord shows them: verse quoted line by line, and its "author" small underneath."""
    shown, verse = [], False
    for paragraph in entry["text"].split("\n\n"):
        if verse and "\n" not in paragraph and len(paragraph) <= ATTRIBUTION:
            shown[-1] += f"\n-# {escape(paragraph)}"
            verse = False
            continue
        verse = "\n" in paragraph
        shown.append("\n".join(f"> {escape(line)}" for line in paragraph.split("\n")) if verse
                     else escape(" ".join(paragraph.split())))  # Prose: one space between sentences
    return shown


def entry_text(entry: dict, limit: int = oldbooks.LONGEST) -> str:
    """The entry, its part of speech first, as much as fits in `limit`."""
    parts = paragraphs(entry) or [""]
    if entry["pos"]:
        parts[0] = f"*{escape(entry['pos'])}* {parts[0]}"
    return oldbooks.fit(parts, limit)


def entry_embed(entries: list[dict]) -> discord.Embed:
    """An entry, or a word's entries ("REASON" is both a verb and a noun)."""
    first = entries[0]
    limit = oldbooks.LONGEST // len(entries)
    description = "\n\n".join(entry_text(entry, limit) for entry in entries)
    embed = discord.Embed(title=f"😈 {escape(first['word'])}"[:256], url=url(first), description=description[:4096],
                          color=COLOUR)
    embed.set_footer(text=SOURCE)
    return embed


def devils_embed(query: str | None) -> discord.Embed:
    """A word looked up, the entries that use it, or (nothing typed) a random one."""
    if not query or not query.strip():
        return entry_embed(DICTIONARY.same_name(random.choice(DICTIONARY.entries)))
    found = DICTIONARY.look_up(query)
    if found and found.kind == "uses":
        return oldbooks.uses_embed(found.entries, title=f"😈 Bierce on “{oldbooks.shown_typed(query)}”",
                                   name=lambda e: escape(e["word"]), query=query, text=lambda e: e["text"],
                                   link=url, source=SOURCE, colour=COLOUR)
    if found:  # The word itself (all its entries), or one spelt like it
        return entry_embed(found.entries if found.kind == "exact" else DICTIONARY.same_name(found.entries[0]))
    return discord.Embed(title=f"😈 {oldbooks.shown_typed(query)}", color=COLOUR,
                         description="Bierce never got round to that one, which is the nicest thing he never said. "
                                     "Try a plain word (money, love, lawyer) to see what he made of it.")


@commands.hybrid_command(name="devils", aliases=["devil", "devilsdictionary"],
                         description="Ambrose Bierce's cynical definition of a word, or a random one.")
@app_commands.describe(word="A word to look up (bore, lawyer, love...). Empty: random")
async def devils(ctx: commands.Context, *, word: str | None = None):
    await ctx.send(embed=devils_embed(word))


@devils.autocomplete("word")
async def word_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


async def setup(bot: commands.Bot):
    bot.add_command(devils)
