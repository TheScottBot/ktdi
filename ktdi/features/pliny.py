"""/pliny [topic]: Pliny the Elder's Natural History (AD 77, in Bostock and Riley's 1855 translation, public domain),
in which a Roman admiral wrote down everything anyone ever told him: elephants that worship the moon, the basilisk,
showers of milk and baked tiles, mares impregnated by the wind.

The chapters are in ktdi/lib/pliny.json, built by ktdi/tools/pliny_build.py from a hand-read allowlist. /pliny on its
own is a random chapter; /pliny <topic> finds one about it (his chapter titles: "The docility of the elephant"), or
one that mentions it, and says if there are more. Each links to its place in the book.
"""

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "🔮 Old oddities"
DATA = Path(__file__).resolve().parent.parent / "lib" / "pliny.json"
SOURCE = "Pliny the Elder, Natural History (AD 77)"
COLOUR = discord.Color.from_rgb(165, 42, 42)  # Imperial purple-ish red
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}

CHAPTERS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["chapters"]


def dictionary(chapters: list[dict]) -> oldbooks.Dictionary:
    # A chapter's title comes first, so chapters about the topic come before ones that mention it.
    return oldbooks.Dictionary(chapters, names=lambda c: [c["title"]], text=lambda c: f"{c['title']}. {c['text']}")


DICTIONARY = dictionary(CHAPTERS)


def arabic(roman: str) -> int:
    """"VIII" is 8, "XXXVII" is 37."""
    values = [ROMAN[letter] for letter in roman]
    return sum(-v if i + 1 < len(values) and v < values[i + 1] else v for i, v in enumerate(values))


def url(chapter: dict) -> str:
    """The volume it's in, scrolled to the chapter (by words with no footnote mark among them on the page)."""
    return links.gutenberg(chapter["volume"], chapter.get("anchor") or chapter["text"])


def chapter_embed(chapter: dict, others: int = 0) -> discord.Embed:
    text = oldbooks.fit([oldbooks.escape(p) for p in chapter["text"].split("\n\n")], oldbooks.LONGEST)
    embed = discord.Embed(title=f"🏛️ {oldbooks.escape(chapter['title'])}"[:256], url=url(chapter), description=text,
                          color=COLOUR)
    where = f"book {arabic(chapter['book'])}, chapter {chapter['chapter']}"
    more = f" He has more on that: ask again ({others + 1} chapters)." if others else ""
    embed.set_footer(text=f"{SOURCE}, {where}.{more}")
    return embed


def pliny_embed(topic: str | None) -> discord.Embed:
    """A chapter on the topic, or (no topic) any."""
    found = DICTIONARY.one_of(topic)
    if not found:
        return discord.Embed(title=f"🏛️ {oldbooks.shown_typed(topic)}", color=COLOUR,
                             description="Astonishingly, Pliny never heard anything about that. Try elephants, "
                                         "dragons, the phoenix, amber, lightning, or the basilisk.")
    return chapter_embed(*found)


@commands.hybrid_command(name="pliny", aliases=["naturalhistory"],
                         description="Pliny the Elder's Natural History (AD 77): confidently, gloriously wrong.")
@app_commands.describe(topic="An animal, stone, marvel or anything (elephants, dragons, amber...). Empty: random")
async def pliny(ctx: commands.Context, *, topic: str | None = None):
    """A chapter of Pliny the Elder's Natural History, in which a Roman admiral wrote down everything anyone ever told
    him: elephants that worship the moon, the basilisk that kills with a look, showers of milk and baked tiles, mares
    impregnated by the wind. Give a topic (elephants, dragons, the phoenix, amber, lightning) for a chapter about it;
    his chapter titles autocomplete. Ask again for another on the same topic. On its own: any chapter."""
    await ctx.send(embed=pliny_embed(topic))


@pliny.autocomplete("topic")
async def topic_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


async def setup(bot: commands.Bot):
    bot.add_command(pliny)
