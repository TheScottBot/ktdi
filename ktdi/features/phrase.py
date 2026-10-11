"""/phrase [idiom]: where an idiom comes from, according to the Rev. E. Cobham Brewer's Dictionary of Phrase and Fable
(1898, public domain), who was very sure of himself.

The idioms are hand-picked from the archive.org scan into ktdi/lib/phrases.json, the OCR mended against the page:
only phrases people still use or would want to know about (not Brewer's thousands of gods, saints and poets), each
with his explanation and its page in the scan. /phrase on its own is a random one; /phrase <idiom> finds the nearest
idiom however it's worded ("raining cats and dogs" finds "To rain cats and dogs"), or failing that the idioms whose
explanations mention it.
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
DATA = Path(__file__).resolve().parent.parent / "lib" / "phrases.json"
SOURCE = "Brewer, Dictionary of Phrase and Fable (1898)"
BOOK = "dictionaryofphra0000ecob"  # The archive.org scan
COLOUR = discord.Color.gold()
CONFIDENCE = [
    "Brewer was certain.",
    "Brewer did not take questions.",
    "Source: the Reverend's own confidence.",
    "Peer-reviewed by Brewer.",
    "As settled as anything ever was in 1898.",
    "The committee has not checked this and will not be doing so.",
]

PHRASES: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))
DICTIONARY = oldbooks.Dictionary(PHRASES, names=lambda entry: [entry["phrase"]], text=lambda entry: entry["text"],
                                 close_first=True)


def escape(text: str) -> str:
    return discord.utils.escape_markdown(text)


def highlight(phrase: str) -> str | None:
    """The word for the scan to highlight: the phrase's longest plain word (archive.org's search trips on
    apostrophes and hyphens)."""
    plain = [word for word in fuzzy.words(phrase) if word.isalpha()]
    return max(plain, key=len) if plain else None


def url(entry: dict) -> str:
    """The scan, open at the idiom's page, with its main word highlighted."""
    return links.archive_page(BOOK, entry.get("page"), highlight(entry["phrase"]))


def phrase_embed(entry: dict) -> discord.Embed:
    text = oldbooks.fit([escape(paragraph) for paragraph in entry["text"].split("\n\n")], oldbooks.LONGEST)
    embed = discord.Embed(title=f"🗣️ {escape(entry['phrase'])}"[:256], url=url(entry),
                          description=f"{text}\n\n-# {random.choice(CONFIDENCE)}"[:4096], color=COLOUR)
    embed.set_footer(text=SOURCE)
    return embed


def explain(query: str | None) -> discord.Embed:
    """An idiom looked up (the nearest one), the idioms whose explanations mention it, or a random one."""
    if not query or not fuzzy.words(query):
        return phrase_embed(random.choice(DICTIONARY.entries))
    found = DICTIONARY.look_up(query)
    if found and found.kind == "uses":
        return oldbooks.uses_embed(found.entries, title=f"🗣️ Idioms that mention “{oldbooks.shown_typed(query)}”",
                                   name=lambda e: escape(e["phrase"]), query=query, text=lambda e: e["text"],
                                   link=url, source=SOURCE, colour=COLOUR)
    if found:
        return phrase_embed(found.entries[0])
    return discord.Embed(title=f"🗣️ {oldbooks.shown_typed(query)}", color=COLOUR,
                         description="Brewer had nothing to say about that, which was rare for him. Try the idiom's "
                                     "main word (cats, hatter, bag).")


@commands.hybrid_command(name="phrase", aliases=["idiom", "brewer"],
                         description="Where an idiom comes from, according to Brewer (1898). Or a random one.")
@app_commands.describe(idiom="An idiom or saying (raining cats and dogs, mad as a hatter...). Empty: random")
async def phrase(ctx: commands.Context, *, idiom: str | None = None):
    """Where an idiom comes from, according to Brewer's Dictionary of Phrase and Fable (1898). Word it however you like
    (raining cats and dogs finds To rain cats and dogs); for a word that isn't an idiom, you get the idioms that
    mention it. On its own: a random one."""
    await ctx.send(embed=explain(idiom))


@phrase.autocomplete("idiom")
async def idiom_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


async def setup(bot: commands.Bot):
    bot.add_command(phrase)
