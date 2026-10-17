"""/esoteric book:talisman [thing] (typed: !talisman [thing]): a talisman, charm or sign of the zodiac and the stones
that go with it, from William Thomas and Kate Pavitt's The Book of Talismans, Amulets and Zodiacal Gems (1914; second
edition 1922; Project Gutenberg): the ankh, the scarab and the Eye of Horus, Chinese and Japanese charms, Gnostic gems,
posy rings and the pentagram, and a chapter for each sign of the zodiac with its stones, planet and famous gems.

The passages are in ktdi/lib/talismans.json, built by ktdi/tools/talisman_build.py from a hand-read allowlist: a
paragraph, or a short run of them, each titled and filed under its chapter, with the book's drawing of it where the
passage cites one (or, in the zodiac chapters, the book's frontispiece of the signs' gems). !talisman on its own is
a random one; !talisman <thing> finds one about it (scarab, aries, dragon, diamond), else one that mentions it, and
says if there are more. The Pavitts wrote as believers; the footer says it's their account.
"""

import json
from pathlib import Path

import discord
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "🐉 Beasts & magic"
DATA = Path(__file__).resolve().parent.parent / "lib" / "talismans.json"
BOOK = 78789  # Project Gutenberg
SOURCE = "W. T. and K. Pavitt, The Book of Talismans, Amulets and Zodiacal Gems (1922)"
EMOJI = "🧿"
COLOUR = discord.Color.from_rgb(201, 162, 39)  # Old gold
CAPTION = 200  # How much of a picture's caption is shown under it

TALISMANS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["talismans"]


def dictionary(talismans: list[dict]) -> oldbooks.Dictionary:
    """By title and other names (scarab, aries, diamond), even misspelt; then by what the passages say."""
    return oldbooks.Dictionary(talismans, names=lambda t: [t["title"], *t.get("also", [])],
                               text=lambda t: f"{t['title']}. {t['text']}", close_first=True)


DICTIONARY = dictionary(TALISMANS)


def url(talisman: dict) -> str:
    """The book, scrolled to the passage's opening words."""
    return links.gutenberg(BOOK, talisman["text"].split("\n")[0].replace("_", ""))


def talisman_embed(talisman: dict, others: int = 0) -> discord.Embed:
    embed = oldbooks.passage_embed(talisman, others, emoji=EMOJI, colour=COLOUR, link=url(talisman),
                                   footer=f"{SOURCE}: {talisman['where']}. The Pavitts' beliefs, not checked facts",
                                   more="There's more where that came from: ask again ({n} passages).")
    if talisman.get("picture"):
        embed.set_image(url=talisman["picture"]["url"])
        embed.add_field(name="In the picture", inline=False,
                        value=oldbooks.escape(oldbooks.clip(talisman["picture"]["caption"], CAPTION)))
    return embed


def talismans_embed(thing: str | None) -> discord.Embed:
    """A passage about what was asked, or (nothing asked) any."""
    return oldbooks.one_passage(DICTIONARY, thing, talisman_embed, emoji=EMOJI, colour=COLOUR,
                                nothing="No talisman for that here. Try a scarab, the ankh, a dragon, a posy ring, or "
                                        "your star sign.")


@commands.command(name="talisman", aliases=["talismans", "amulet", "zodiac"],
                  description="A talisman, charm or star sign and its stones "
                              "(The Book of Talismans, 1922).")
async def talisman(ctx: commands.Context, *, thing: str | None = None):
    """A talisman or charm and what it was for, or a sign of the zodiac and its stones, from William Thomas and Kate
    Pavitt's The Book of Talismans, Amulets and Zodiacal Gems (1922): the ankh, the scarab and the Eye of Osiris,
    Chinese and Japanese charms, Gnostic gems, the pentagram, posy rings and gemmel rings, and a chapter for each star
    sign with its stones, its planet and the famous gems that go with it. Give a thing (`/esoteric book:talisman
    thing:scarab`), a sign (`leo`) or a stone (`opal`) for a passage on it, with the book's drawing of it when there is
    one; the titles autocomplete. Ask again for another. On its own: any. It goes well with `book:gemlore`. William
    Pavitt made talismanic jewellery, and both wrote as believers, so it's their account, not checked fact. Typed,
    `!talismans`, `!amulet` and `!zodiac` work too."""
    await ctx.send(embed=talismans_embed(thing))


OLD_BOOK = oldbooks.OldBook(SOURCE, EMOJI, "talisman", random=lambda: talismans_embed(None),
                            find=lambda thing: DICTIONARY.look_up(thing, close_first=False), link=url,
                            names=lambda: DICTIONARY.names, own_command=False,
                            shelves=("esoteric",))


async def setup(bot: commands.Bot):
    bot.add_command(talisman)
