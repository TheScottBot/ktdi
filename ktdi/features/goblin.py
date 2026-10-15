"""/goblin [what]: a tale from Wirt Sikes's British Goblins (1880; public domain, Project Gutenberg): the fairies,
goblins, spectral hounds, corpse candles, lake maidens, ghosts and old customs of Wales, as people told them to the
American consul in Cardiff, with T. H. Thomas's illustrations where there are any.

The tales are in ktdi/lib/goblin.json, built by ktdi/tools/goblin_build.py from a hand-read allowlist: the book's
short numbered sections, each about one creature, place or incident, titled for the purpose (mostly from the
chapter's own list of topics). /goblin on its own is a random tale; /goblin <what> finds one by its title or other
names (Pwca, Tylwyth Teg, corpse candle), else by what it says, and says if there are more.
"""

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "🐉 Beasts & magic"
DATA = Path(__file__).resolve().parent.parent / "lib" / "goblin.json"
BOOK = 34704  # Project Gutenberg
SOURCE = "Wirt Sikes, British Goblins (1880)"
EMOJI = "🧚"
COLOUR = discord.Color.from_rgb(0, 122, 61)  # The green of the Welsh flag

TALES: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["tales"]


def dictionary(tales: list[dict]) -> oldbooks.Dictionary:
    """By title and other names (a creature's Welsh and English ones, the place), even misspelt; then by what the
    tales say."""
    return oldbooks.Dictionary(tales, names=lambda t: [t["title"], *t.get("also", [])],
                               text=lambda t: f"{t['title']}. {t['text']}", close_first=True)


DICTIONARY = dictionary(TALES)


def url(tale: dict) -> str:
    """The book, scrolled to the tale's opening words."""
    return links.gutenberg(BOOK, tale["text"].split("\n")[0].replace("_", ""))


def tale_embed(tale: dict, others: int = 0) -> discord.Embed:
    embed = oldbooks.passage_embed(tale, others, emoji=EMOJI, colour=COLOUR, link=url(tale),
                                   footer=f"{SOURCE}: {tale['book_title']}",
                                   more="Wales has more on that: ask again ({n} tales).")
    if tale["images"]:
        embed.set_image(url=tale["images"][0]["url"])
    return embed


def goblin_embed(what: str | None) -> discord.Embed:
    """A tale about what was asked, or (nothing asked) any."""
    return oldbooks.one_passage(DICTIONARY, what, tale_embed, emoji=EMOJI, colour=COLOUR,
                                nothing="Sikes heard no tale of that in all Wales. Try the Pwca, corpse candles, the "
                                        "Tylwyth Teg, lake maidens or the Cŵn Annwn.")


@commands.hybrid_command(name="goblin", aliases=["goblins", "fairies"],
                         description="Welsh fairies, goblins, ghosts and customs, from British Goblins (1880).")
@app_commands.describe(what="A creature, place or custom (pwca, corpse candle, lake maiden...). Empty: random")
async def goblin(ctx: commands.Context, *, what: str | None = None):
    """A tale from Wirt Sikes's British Goblins (1880), the folklore of Wales as people told it to the American
    consul in Cardiff: the Tylwyth Teg (the fair folk), the Pwca, mine goblins that knock, lake maidens, corpse
    candles, spectral hounds, ghosts, old wedding and funeral customs, and legends of bells, wells, stones and
    dragons, with T. H. Thomas's illustrations where there are any. Give a creature, place or custom (pwca, corpse
    candle, lake maiden, sin-eater) for a tale about it; the titles autocomplete, and Welsh and English names both
    work. Ask again for another. On its own: any tale. Typed, `!goblins` and `!fairies` work too."""
    await ctx.send(embed=goblin_embed(what))


@goblin.autocomplete("what")
async def what_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


OLD_BOOK = oldbooks.OldBook(SOURCE, EMOJI, "goblin", random=lambda: goblin_embed(None),
                            find=lambda what: DICTIONARY.look_up(what, close_first=False), link=url)


async def setup(bot: commands.Bot):
    bot.add_command(goblin)
