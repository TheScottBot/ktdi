"""/nature book:wonder [topic] (typed: !wonder [topic]): a curiosity from Ten Thousand Wonderful Things (ed. Edmund
Fillingham King, 1894; public domain, Project Gutenberg), a Victorian cabinet of curiosities: remarkable objects,
customs, eccentric people, inventions, animals and extraordinary claims, many with an engraving, which is shown with it.

The curiosities are in ktdi/lib/wonder.json, built by ktdi/tools/wonder_build.py from a hand-read allowlist. Each
is numbered in book order ("Wonder No. 312": the book doesn't number them). !wonder on its own is a random one;
!wonder <topic> finds one about it, by its title or what it says, and says if there are more. They're the book's
claims, not checked facts, and the footer says so.
"""

import json
from pathlib import Path

import discord
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "🐉 Beasts & magic"
DATA = Path(__file__).resolve().parent.parent / "lib" / "wonder.json"
BOOK = 45849  # Project Gutenberg
SOURCE = "Ten Thousand Wonderful Things (1894 edition)"
EMOJI = "✨"
COLOUR = discord.Color.from_rgb(176, 141, 87)  # Brass, like a cabinet's fittings

WONDERS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["wonders"]


def dictionary(wonders: list[dict]) -> oldbooks.Dictionary:
    return oldbooks.titled(wonders)


DICTIONARY = dictionary(WONDERS)


def url(wonder: dict) -> str:
    """The book, scrolled to the curiosity's opening words."""
    return links.gutenberg(BOOK, wonder["text"].split("\n")[0].replace("_", ""))


def wonder_embed(wonder: dict, others: int = 0) -> discord.Embed:
    embed = oldbooks.passage_embed(wonder, others, emoji=EMOJI, colour=COLOUR, link=url(wonder),
                                   footer=f"Wonder No. {wonder['number']}, from {SOURCE}. The book's claims, not "
                                          f"checked facts",
                                   more="The cabinet has more on that: ask again ({n} wonders).")
    if wonder["images"]:
        embed.set_image(url=wonder["images"][0]["url"])
    return embed


def wonders_embed(topic: str | None) -> discord.Embed:
    """A curiosity on the topic, or (no topic) any."""
    return oldbooks.one_passage(DICTIONARY, topic, wonder_embed, emoji=EMOJI, colour=COLOUR,
                                nothing="Nothing on that in this cabinet. Try giants, "
                                        "clocks, coffee, swans, hoops or highwaymen.")


@commands.command(name="wonder", aliases=["wonders", "curiosity"],
                  description="A Victorian curiosity from Ten Thousand Wonderful Things, engraving and all.")
async def wonder(ctx: commands.Context, *, topic: str | None = None):
    """A curiosity from Ten Thousand Wonderful Things (first published about 1860; this is the 1894 edition), a
    Victorian cabinet of curiosities: remarkable objects,
    old customs, eccentrics, inventions, animals and extraordinary claims, with the book's engraving when it has one.
    On its own: a random one, for stumbling on something odd. Give a topic (giants, clocks, coffee, swans,
    highwaymen) for one about it (the titles autocomplete); ask again for another. Each is numbered (Wonder No. 312)
    and links to its place in the book. They're the book's claims, as it made them, not checked facts.
    Typed, `!wonders` and `!curiosity` work too."""
    await ctx.send(embed=wonders_embed(topic))


OLD_BOOK = oldbooks.OldBook(SOURCE, EMOJI, "wonder", random=lambda: wonders_embed(None),
                            find=lambda topic: DICTIONARY.look_up(topic), link=url,
                            names=lambda: DICTIONARY.names, own_command=False,
                            shelves=("nature", "folklore"))


async def setup(bot: commands.Bot):
    bot.add_command(wonder)
