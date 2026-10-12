"""/bestiary [beast]: Edward Topsell's The Historie of Foure-footed Beastes (1607) and The Historie of Serpents (1608),
public domain, in which a Jacobean clergyman gathered everything ever said about every animal, believed nearly all of
it, and put the unicorn, the gorgon and the winged dragon in among the badgers and the cats.

The passages are in ktdi/lib/bestiary.json, built by ktdi/tools/bestiary_build.py from a hand-read allowlist: single
paragraphs, in the books' own spelling, each filed under a modern name for its beast ("Unicorn" for "OF THE
VNICORNE"). /bestiary on its own is a random passage; /bestiary <beast> finds one about it (or, failing that, one
that mentions it) and says if there are more. Each links to its page in the scan of the printed book.
"""

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "🔮 Old oddities"
DATA = Path(__file__).resolve().parent.parent / "lib" / "bestiary.json"
BOOKS = {
    "beasts": ("The Historie of Foure-footed Beastes (1607)",
               "bim_early-english-books-1475-1640_the-historie-of-foure-fo_topsell-edward_1607"),
    "serpents": ("The Historie of Serpents (1608)",
                 "bim_early-english-books-1475-1640_the-historie-of-serpents_topsell-edward_1608"),
}
EMOJI = "🐉"
COLOUR = discord.Color.from_rgb(46, 110, 72)  # Dragon green

PASSAGES: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["passages"]


def dictionary(passages: list[dict]) -> oldbooks.Dictionary:
    """Looked up by the beast's modern name (and any others it goes by), even misspelt, then by what the passages
    say, searched in modern spelling ("loue" is found by "love")."""
    return oldbooks.Dictionary(passages, names=lambda p: [p["name"], *p.get("also", [])],
                               text=lambda p: oldbooks.modern_spelling(f"{p['name']}. {p['text']}"), close_first=True)


DICTIONARY = dictionary(PASSAGES)


def url(passage: dict) -> str:
    """The scan of the printed book, open at the passage's page, with a word of it highlighted."""
    return links.archive_page(BOOKS[passage["book"]][1], passage["page"], passage.get("highlight"))


def passage_embed(passage: dict, others: int = 0) -> discord.Embed:
    book = BOOKS[passage["book"]][0]
    page = f", page {passage['folio']}" if passage.get("folio") else ""
    shown = {**passage, "title": passage["name"]}
    return oldbooks.passage_embed(shown, others, emoji=EMOJI, colour=COLOUR, link=url(passage),
                                  footer=f"Edward Topsell, {book}: \"{passage['head']}\"{page}",
                                  more="He has more on that beast: ask again ({n} passages).")


def bestiary_embed(beast: str | None) -> discord.Embed:
    """A passage on the beast, or (no beast) any."""
    return oldbooks.one_passage(DICTIONARY, beast, passage_embed, emoji=EMOJI, colour=COLOUR,
                                nothing="Topsell never heard of that one, which is saying something. Try the "
                                        "unicorn, the dragon, the elephant, the hedgehog, or the cockatrice.")


@commands.hybrid_command(name="bestiary", aliases=["topsell"],
                         description="Topsell's bestiary (1607): unicorns, dragons and badgers, all equally real.")
@app_commands.describe(beast="An animal, real or otherwise (unicorn, dragon, elephant, toad...). Empty: random")
async def bestiary(ctx: commands.Context, *, beast: str | None = None):
    """A passage from Edward Topsell's bestiary: The Historie of Foure-footed Beastes (1607) and The Historie of
    Serpents (1608), in which a Jacobean clergyman gathered everything ever said about every animal, believed nearly
    all of it, and put the unicorn, the gorgon and the winged dragon in among the badgers and the cats. Give a beast
    (unicorn, dragon, elephant, hedgehog, cockatrice, toad) for a passage about it; the beasts autocomplete. Ask again
    for another on the same beast. On its own: any passage. It's in his own 1607 spelling (u and v swap: "Vnicorne",
    "haue"), and links to the page in the printed book. Typed, `!topsell` works too."""
    await ctx.send(embed=bestiary_embed(beast))


@bestiary.autocomplete("beast")
async def beast_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


async def setup(bot: commands.Bot):
    bot.add_command(bestiary)
