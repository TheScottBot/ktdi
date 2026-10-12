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
from ktdi.lib import links, roman

HELP_CATEGORY = "🐉 Beasts & magic"
DATA = Path(__file__).resolve().parent.parent / "lib" / "pliny.json"
SOURCE = "Pliny the Elder, Natural History (AD 77)"
COLOUR = discord.Color.from_rgb(165, 42, 42)  # Imperial purple-ish red

CHAPTERS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["chapters"]


def dictionary(chapters: list[dict]) -> oldbooks.Dictionary:
    return oldbooks.titled(chapters)


DICTIONARY = dictionary(CHAPTERS)


def url(chapter: dict) -> str:
    """The volume it's in, scrolled to the chapter (by words with no footnote mark among them on the page)."""
    return links.gutenberg(chapter["volume"], chapter.get("anchor") or chapter["text"])


def chapter_embed(chapter: dict, others: int = 0) -> discord.Embed:
    where = f"book {roman.to_int(chapter['book'])}, chapter {chapter['chapter']}"
    return oldbooks.passage_embed(chapter, others, emoji="🏛️", colour=COLOUR, link=url(chapter),
                                  footer=f"{SOURCE}, {where}", more="He has more on that: ask again ({n} chapters).")


def pliny_embed(topic: str | None) -> discord.Embed:
    """A chapter on the topic, or (no topic) any."""
    return oldbooks.one_passage(DICTIONARY, topic, chapter_embed, emoji="🏛️", colour=COLOUR,
                                nothing="Astonishingly, Pliny never heard anything about that. Try elephants, "
                                        "dragons, the phoenix, amber, lightning, or the basilisk.")


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


OLD_BOOK = oldbooks.OldBook(SOURCE, "🏛️", "pliny", random=lambda: pliny_embed(None),
                            find=lambda topic: DICTIONARY.look_up(topic), link=url)



async def setup(bot: commands.Bot):
    bot.add_command(pliny)
