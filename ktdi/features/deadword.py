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

from ktdi.common import choices
from ktdi.lib import fuzzy, links

HELP_CATEGORY = "📜 Old books"
DATA = Path(__file__).resolve().parent.parent / "lib" / "deadwords.json"
SOURCE = "Mackay, Lost Beauties of the English Language (1874)"
BOOK = "cu31924096224880"  # The archive.org scan
SOURCE_URL = links.archive_page(BOOK, None)
SHOWN = 8  # Dead words listed when a word turns up in several meanings.
LINE_LENGTH = 140

WORDS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))
INDEX = fuzzy.index((entry, entry["word"]) for entry in WORDS)
ALL_WORDS = sorted({entry["word"] for entry in WORDS}, key=str.casefold)

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


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:text.rfind(" ", 0, limit - 1)].rstrip(",;:") + "…"


def word_embed(entry: dict) -> discord.Embed:
    meaning = entry["meaning"].strip()
    description = f"*{escape(meaning[0].upper() + meaning[1:])}*"
    if entry.get("quote"):
        quote = "\n".join(f"> {escape(line.strip())}" for line in entry["quote"].split(" / "))
        source = f"\n-# {escape(entry['quote_source'])}" if entry.get("quote_source") else ""
        description += f"\n\n{quote}{source}"
    description += f"\n\n🪦 {random.choice(EPITAPHS)}"
    url = links.archive_page(BOOK, entry.get("page"), entry["word"])  # Open at its page, highlighted
    embed = discord.Embed(title=f"📜 {escape(entry['word'])}"[:256], url=url, description=description[:4096],
                          color=discord.Color.dark_grey())
    embed.set_footer(text=SOURCE)
    return embed


def in_meanings(query: str) -> list[dict]:
    """Dead words whose meanings use every word typed ("drink": bever, bicker...)."""
    return fuzzy.containing(query, WORDS, lambda entry: entry["meaning"], meaning_first=False)


def deadword_embed(query: str | None) -> discord.Embed:
    """A word looked up, the dead words that meant it, or (nothing typed) a random one."""
    if not query or not fuzzy.words(query):
        return word_embed(random.choice(WORDS))
    match = fuzzy.best_match(query, INDEX, spelling=fuzzy.STRICT_SPELLING)
    if match and match.exact:  # It's one of the dead words.
        return word_embed(match.thing)
    found = in_meanings(query)
    if found:
        shown = random.sample(found, min(SHOWN, len(found)))
        lines = [clip(f"**{escape(e['word'])}**: {escape(e['meaning'])}", LINE_LENGTH) for e in shown]
        typed = escape(" ".join(query.split())[:60])
        embed = discord.Embed(title=f"📜 Dead words for “{typed}”"[:256], url=SOURCE_URL,
                              description="\n".join(lines), color=discord.Color.dark_grey())
        more = f". Showing {len(shown)} of {len(found)}: ask again for others." if len(found) > len(shown) else ""
        embed.set_footer(text=f"{SOURCE}{more}")
        return embed
    if match:  # Nothing meant it, but a dead word looks like it.
        return word_embed(match.thing)
    typed = escape(" ".join(query.split())[:60])
    return discord.Embed(title=f"📜 {typed}", color=discord.Color.dark_grey(),
                         description="Mackay never mourned that one. It may still be alive. Try a plain word "
                                     "(drink, fool, morning) to find the dead words for it.")


@commands.hybrid_command(name="deadword", description="A word English stopped using. Look one up, or get a random one.")
@app_commands.describe(word="A dead word to look up, or a plain one (drink, fool...) to find dead words for. "
                            "Empty: random")
async def deadword(ctx: commands.Context, *, word: str | None = None):
    await ctx.send(embed=deadword_embed(word))


@deadword.autocomplete("word")
async def word_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return choices(fuzzy.starting_first(current, ALL_WORDS) if current.strip() else random.sample(ALL_WORDS, 25))


async def setup(bot: commands.Bot):
    bot.add_command(deadword)
