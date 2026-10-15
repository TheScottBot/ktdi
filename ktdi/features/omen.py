"""/omen [what]: an everyday superstition from Robert Means Lawrence's The Magic of the Horse-shoe, with Other Folk-Lore
Notes (1898; public domain, Project Gutenberg): why a horseshoe is lucky, spilling salt, blessing a sneeze, unlucky
Fridays, rats served with legal notices, the luck of odd numbers and the ill luck of thirteen.

The omens are in ktdi/lib/omen.json, built by ktdi/tools/omen_build.py from a hand-read allowlist: a paragraph, or a
short run of them, each titled for what it's about and filed under the book's essay and subsection. /omen on its
own is a random one; /omen <what> finds one by its title or other names (salt, thirteen, sneezing), else by what it
says, and says if there are more.
"""

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "🐉 Beasts & magic"
DATA = Path(__file__).resolve().parent.parent / "lib" / "omen.json"
BOOK = 57411  # Project Gutenberg
SOURCE = "Robert Means Lawrence, The Magic of the Horse-shoe (1898)"
EMOJI = "🍀"
COLOUR = discord.Color.from_rgb(112, 128, 144)  # Horseshoe iron

OMENS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["omens"]


def dictionary(omens: list[dict]) -> oldbooks.Dictionary:
    """By title and other names (salt, Friday, thirteen), even misspelt; then by what the passages say."""
    return oldbooks.Dictionary(omens, names=lambda o: [o["title"], *o.get("also", [])],
                               text=lambda o: f"{o['title']}. {o['text']}", close_first=True)


DICTIONARY = dictionary(OMENS)


def url(omen: dict) -> str:
    """The book, scrolled to the passage's opening words."""
    return links.gutenberg(BOOK, omen["text"].split("\n")[0].replace("_", ""))


def omen_embed(omen: dict, others: int = 0) -> discord.Embed:
    return oldbooks.passage_embed(omen, others, emoji=EMOJI, colour=COLOUR, link=url(omen),
                                  footer=f"{SOURCE}: {omen['essay_title']}, {omen['section_title']}",
                                  more="There's more where that came from: ask again ({n} omens).")


def omens_embed(what: str | None) -> discord.Embed:
    """An omen about what was asked, or (nothing asked) any."""
    return oldbooks.one_passage(DICTIONARY, what, omen_embed, emoji=EMOJI, colour=COLOUR,
                                nothing="No omen about that here. Try salt, sneezing, Friday, thirteen, horseshoes "
                                        "or the number seven.")


@commands.hybrid_command(name="omen", aliases=["omens", "superstition"],
                         description="An everyday superstition and where it came from "
                                     "(The Magic of the Horse-shoe, 1898).")
@app_commands.describe(what="A superstition or omen (salt, sneezing, Friday, thirteen, horseshoes...). Empty: random")
async def omen(ctx: commands.Context, *, what: str | None = None):
    """An everyday superstition and where it came from, from Robert Means Lawrence's The Magic of the Horse-shoe
    (1898): why a horseshoe over the door is lucky (and which way up), spilling salt, blessing a sneeze, unlucky
    Fridays and lucky days, rats and caterpillars served with legal notices, charms against animals, the luck of odd
    numbers and the ill luck of thirteen. Give one (salt, sneezing, Friday, thirteen, horseshoes) for a passage on
    it; the titles autocomplete. Ask again for another. On its own: any omen. Typed, `!omens` and `!superstition`
    work too."""
    await ctx.send(embed=omens_embed(what))


@omen.autocomplete("what")
async def what_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


OLD_BOOK = oldbooks.OldBook(SOURCE, EMOJI, "omen", random=lambda: omens_embed(None),
                            find=lambda what: DICTIONARY.look_up(what, close_first=False), link=url)


async def setup(bot: commands.Bot):
    bot.add_command(omen)
