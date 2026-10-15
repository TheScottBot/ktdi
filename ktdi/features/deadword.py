"""/deadword [word]: a word English has stopped using, from Charles Mackay's Lost Beauties of the English Language (1874,
public domain), a book written to bring them back.

The words are hand-picked from the archive.org scan into ktdi/lib/deadwords.json: only ones that are really dead now
(Mackay also championed words that recovered, like "besmirch"), each with his definition and, where there's a good
one, a line showing it in use. /deadword on its own is a random one; /deadword <word> looks one up (any word order,
small typos), or failing that finds the dead words that meant it ("drink" gets bever, bicker...).
"""

import json
import random
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import fuzzy, links

HELP_CATEGORY = "📚 Words & wisdom"
DATA = Path(__file__).resolve().parent.parent / "lib" / "deadwords.json"
SOURCE = "Mackay, Lost Beauties of the English Language (1874)"
BOOK = "cu31924096224880"  # The archive.org scan
COLOUR = discord.Color.dark_grey()

WORDS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))
DICTIONARY = oldbooks.Dictionary(WORDS, names=lambda entry: [entry["word"]], text=lambda entry: entry["meaning"],
                                 meaning_first=False)

EPITAPHS = [
    "Here lies a perfectly good word.",
    "Gone, but not forgotten. Well, forgotten.",
    "Taken from us too soon.",
    "Survived by its duller synonyms.",
    "Rest in peace. Use in conversation.",
    "Last seen in 1874, being championed by Charles Mackay.",
    "It did nothing wrong.",
    "The committee moves that it be brought back.",
]


def escape(text: str) -> str:
    return discord.utils.escape_markdown(text)


def url(entry: dict) -> str:
    """The scan, open at the word's page, with the word highlighted."""
    return links.archive_page(BOOK, entry.get("page"), entry["word"])


def word_embed(entry: dict) -> discord.Embed:
    meaning = entry["meaning"].strip()
    description = f"*{escape(meaning[0].upper() + meaning[1:])}*"
    if entry.get("quote"):
        quote = "\n".join(f"> {escape(line.strip())}" for line in entry["quote"].split(" / "))
        source = f"\n-# {escape(entry['quote_source'])}" if entry.get("quote_source") else ""
        description += f"\n\n{quote}{source}"
    description += f"\n\n🪦 {random.choice(EPITAPHS)}"
    embed = discord.Embed(title=f"📜 {escape(entry['word'])}"[:256], url=url(entry), description=description[:4096],
                          color=COLOUR)
    embed.set_footer(text=SOURCE)
    return embed


def deadword_embed(query: str | None) -> discord.Embed:
    """A word looked up, the dead words that meant it, or (nothing typed) a random one."""
    if not query or not fuzzy.words(query):
        return word_embed(random.choice(DICTIONARY.entries))
    found = DICTIONARY.look_up(query)
    if found and found.kind == "uses":  # Not one of the dead words, but some of them meant it
        return oldbooks.uses_embed(found.entries, title=f"📜 Dead words for “{oldbooks.shown_typed(query)}”",
                                   name=lambda e: escape(e["word"]), query=query, text=lambda e: e["meaning"],
                                   link=url, source=SOURCE, colour=COLOUR)
    if found:  # One of the dead words, or (nothing meant it) one that looks like it
        return word_embed(found.entries[0])
    return discord.Embed(title=f"📜 {oldbooks.shown_typed(query)}", color=COLOUR,
                         description=oldbooks.not_here("That isn't among these dead words. It may still be alive. "
                                                       "Try a plain word (drink, fool, morning) to find the dead "
                                                       "words for it."))


@commands.hybrid_command(name="deadword", description="A word English stopped using. Look one up, or get a random one.")
@app_commands.describe(word="A dead word to look up, or a plain one (drink, fool...) to find dead words for. "
                            "Empty: random")
async def deadword(ctx: commands.Context, *, word: str | None = None):
    """A word English stopped using, from Mackay's Lost Beauties of the English Language (1874): bever (a drink between
    meals), bell-penny (money laid up for your own funeral). Give a dead word to look it up, or a plain one (drink,
    fool) to find the dead words for it. On its own: a random one."""
    await ctx.send(embed=deadword_embed(word))


@deadword.autocomplete("word")
async def word_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


OLD_BOOK = oldbooks.OldBook(SOURCE, "📜", "deadword", random=lambda: deadword_embed(None),
                            find=lambda topic: DICTIONARY.look_up(topic), title=lambda e: e["word"], link=url,
                            text=lambda e: e["meaning"])



async def setup(bot: commands.Bot):
    bot.add_command(deadword)
