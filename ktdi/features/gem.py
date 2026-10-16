"""/gemlore [stone]: a stone and what was believed of it, from George Frederick Kunz's The Curious Lore of Precious
Stones (1913; public domain, Project Gutenberg): talismans and amulets, birthstones, stones of the planets and the
days, crystal balls, the High-Priest's breastplate, cursed and glowing stones, famous jewels.

The passages are in ktdi/lib/gems.json, built by ktdi/tools/gem_build.py from a hand-read allowlist: a paragraph, or
a short run of them, each titled, filed under the book's chapter and section, and named for its stones, and some with
the book's picture of it. /gemlore on its own is a random one; /gemlore <stone> finds one about it (ruby, jade,
January, crystal ball), else one that mentions it, and says if there are more. Kunz looked back over centuries of
writers, and some of what he says they believed is disputed: the footer says so.
"""

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "🐉 Beasts & magic"
DATA = Path(__file__).resolve().parent.parent / "lib" / "gems.json"
BOOK = 57978  # Project Gutenberg
SOURCE = "George Frederick Kunz, The Curious Lore of Precious Stones (1913)"
EMOJI = "💎"
COLOUR = discord.Color.from_rgb(15, 82, 186)  # Sapphire
CAPTION = 300  # How much of a picture's caption is shown under it

GEMS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["gems"]


def dictionary(gems: list[dict]) -> oldbooks.Dictionary:
    """By title and stones and other names (ruby, jade, january), even misspelt; then by what the passages say."""
    return oldbooks.Dictionary(gems, names=lambda g: [g["title"], *g.get("also", [])],
                               text=lambda g: f"{g['title']}. {g['text']}", close_first=True)


DICTIONARY = dictionary(GEMS)


def url(gem: dict) -> str:
    """The book, scrolled to the passage's opening words."""
    return links.gutenberg(BOOK, gem["text"].split("\n")[0].replace("_", ""))


def gem_embed(gem: dict, others: int = 0) -> discord.Embed:
    embed = oldbooks.passage_embed(gem, others, emoji=EMOJI, colour=COLOUR, link=url(gem),
                                   footer=f"{SOURCE}: {gem['where']}. His account of old beliefs: some of the "
                                          f"attributions are disputed",
                                   more="There's more where that came from: ask again ({n} passages).")
    if gem.get("picture"):
        embed.set_image(url=gem["picture"]["url"])
        embed.add_field(name="In the picture", value=oldbooks.escape(oldbooks.clip(gem["picture"]["caption"],
                                                                                   CAPTION)), inline=False)
    return embed


def gems_embed(stone: str | None) -> discord.Embed:
    """A passage about the stone asked for, or (nothing asked) any."""
    return oldbooks.one_passage(DICTIONARY, stone, gem_embed, emoji=EMOJI, colour=COLOUR,
                                nothing="Nothing on that stone here. Try ruby, jade, opal, turquoise, a crystal "
                                        "ball, or your birth month.")


@commands.hybrid_command(name="gemlore", aliases=["gems", "birthstone"],
                         description="A precious stone and what was believed of it "
                                     "(The Curious Lore of Precious Stones, 1913).")
@app_commands.describe(stone="A stone, a month or a thing (ruby, jade, opal, january, crystal ball). Empty: random")
async def gemlore(ctx: commands.Context, *, stone: str | None = None):
    """A precious stone and what people believed of it, from George Frederick Kunz's The Curious Lore of Precious
    Stones (1913): talismans and amulets, what each stone was said to do (agate to turquoise), birthstones and the
    stones of the months, days, planets and zodiac, crystal balls, the High-Priest's breastplate, cursed and glowing
    stones, and famous jewels with stories. Give a stone (ruby, jade, opal), a month (`/gemlore january`) or a thing
    (crystal ball, breastplate) for a passage on it; the titles autocomplete. Ask again for another. On its own: any
    stone. It goes well with `/secrets`, Albertus Magnus's book of stones. Kunz looked back over centuries of
    writers, and some of what he says they believed is disputed. Typed, `!gems` and `!birthstone` work too. Its
    medicine chapter isn't in it."""
    await ctx.send(embed=gems_embed(stone))


@gemlore.autocomplete("stone")
async def stone_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


OLD_BOOK = oldbooks.OldBook(SOURCE, EMOJI, "gemlore", random=lambda: gems_embed(None),
                            find=lambda stone: DICTIONARY.look_up(stone, close_first=False), link=url)


async def setup(bot: commands.Bot):
    bot.add_command(gemlore)
