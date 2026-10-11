"""/dream [thing]: what dreaming of it foretells, from Gustavus Hindman Miller's Ten Thousand Dreams Interpreted (1901,
public domain): "To dream of an eel is good if you can maintain your grip on him."

The entries are in ktdi/lib/dream.json, built by ktdi/tools/dream_build.py from a hand-read allowlist. /dream on its
own is a random dream. /dream <thing> takes a thing ("eel") or the whole dream ("I dreamt my teeth fell out": Teeth),
any word order and small typos; failing that it lists the dreams whose meanings mention it ("landlord"). Each links to
its place in the book.
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
DATA = Path(__file__).resolve().parent.parent / "lib" / "dream.json"
SOURCE = "Miller, Ten Thousand Dreams Interpreted (1901)"
BOOK = 926  # Project Gutenberg
SOURCE_URL = links.gutenberg(BOOK)
COLOUR = discord.Color.purple()
DISCLAIMERS = [
    "The committee accepts no liability for prophecies.",
    "Results may vary. Results have not been tested.",
    "Prophecy valid for one (1) dream only.",
    "Miller's predictions are not covered by spray insurance.",
    "Not a substitute for actual sleep.",
    "If the prophecy comes true, the committee would like a cut.",
]

ENTRIES: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["entries"]


def names(entry: dict) -> list[str]:
    """"Cavern or Cave" is both."""
    return re.split(r" or ", entry["word"])


def dictionary(entries: list[dict]) -> oldbooks.Dictionary:
    return oldbooks.Dictionary(entries, names=names, text=lambda entry: entry["text"])


DICTIONARY = dictionary(ENTRIES)


def escape(text: str) -> str:
    """Escaped for Discord, with the book's _italics_ kept as italics."""
    return re.sub(r"\\_(.+?)\\_", r"*\1*", discord.utils.escape_markdown(text))


def url(entry: dict) -> str:
    """The book, scrolled to the entry's first paragraph (its heading is a block of its own on the page)."""
    return links.gutenberg(BOOK, entry["text"].split("\n\n")[0])


def dream_embed(entry: dict) -> discord.Embed:
    paragraphs = [escape(paragraph) for paragraph in entry["text"].split("\n\n")]
    description = f"{oldbooks.fit(paragraphs, oldbooks.LONGEST)}\n\n-# 🔮 {random.choice(DISCLAIMERS)}"
    embed = discord.Embed(title=f"🔮 {escape(entry['word'])}"[:256], url=url(entry), description=description[:4096],
                          color=COLOUR)
    embed.set_footer(text=SOURCE)
    return embed


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]


def interpret(query: str | None) -> discord.Embed:
    """A dream looked up: the thing (or the thing in a whole dream), the dreams that mention it, or a random one."""
    if not query or not query.strip():
        return dream_embed(random.choice(DICTIONARY.entries))
    found = DICTIONARY.look_up(query)
    if found and found.kind == "exact":
        return dream_embed(found.entries[0])
    named = DICTIONARY.named_in(query)  # "I dreamt my teeth fell out"
    if named:
        return dream_embed(named[0])
    if found and found.kind == "uses":
        return oldbooks.uses_embed(found.entries, title=f"🔮 Dreams that mention “{oldbooks.shown_typed(query)}”",
                                   line=lambda e: f"**{escape(e['word'])}**: {escape(first_sentence(e['text']))}",
                                   source=SOURCE, url=SOURCE_URL, colour=COLOUR)
    if found:  # Spelt like something Miller covered
        return dream_embed(found.entries[0])
    return discord.Embed(title=f"🔮 {oldbooks.shown_typed(query)}", color=COLOUR,
                         description="Miller had nothing on that, which is itself an omen. Try the main thing in the "
                                     "dream (teeth, eels, a ladder, your mother).")


@commands.hybrid_command(name="dream", description="What your dream foretells, according to 1901. Or a random one.")
@app_commands.describe(thing="What you dreamt of (eels, teeth...) or the whole dream. Empty: random")
async def dream(ctx: commands.Context, *, thing: str | None = None):
    await ctx.send(embed=interpret(thing))


@dream.autocomplete("thing")
async def thing_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


async def setup(bot: commands.Bot):
    bot.add_command(dream)
