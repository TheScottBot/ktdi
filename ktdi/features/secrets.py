"""/secrets [what]: The Boke of Secretes of Albertus Magnus (English, 1560, public domain): the magic of herbs, stones
and beasts, and the marvels of the world. Not really by Albertus (a medieval compilation that borrowed his name),
and none of it works, which is the charm: lay a lodestone under your wife's head to learn if she's faithful, carry
marigold and a wolf's tooth so nobody can speak against you, light a lamp that makes whoever holds it fart.

The secrets are in ktdi/lib/secrets.json, built by ktdi/tools/secrets_build.py from a hand-read allowlist (only the
harmless magic). /secrets on its own is a random one; /secrets <what> finds one by what it's for ("enemies",
"invisible", "fire") or what it's made of ("amethyst", "owl"), and says if there are more. Each links to its page in
the scan of the printed book.
"""

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "🐉 Beasts & magic"
DATA = Path(__file__).resolve().parent.parent / "lib" / "secrets.json"
SCAN = "bim_early-english-books-1475-1640_the-boke-of-secretes-of-_albertus-magnus_1560"
SOURCE = "The Boke of Secretes of Albertus Magnus (1560)"
EMOJI = "🗝️"
COLOUR = discord.Color.from_rgb(92, 61, 130)  # Alchemist's purple
HEADED = set(range(2, 47)) | {50, 51, 52}  # Sections whose heading says what the secret is for ("If thou wilt...")

SECRETS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["passages"]


def section(secret: dict) -> int:
    return int(secret["key"].split(":")[1])


def title(secret: dict) -> str:
    """What the secret is for, in the book's words ("If thou wilt make a rayne bowe to appeare"), or (a herb or a
    beast, which the book just describes) what it is."""
    return secret.get("title") or (secret["head"] if section(secret) in HEADED else secret["name"])


def part(secret: dict) -> str:
    """Which part of the book it's from."""
    number = section(secret)
    return "of herbs" if number < 2 else "of stones" if number < 47 else "of beasts" if number < 49 else \
        "the Meruayles of the World"


def dictionary(secrets: list[dict]) -> oldbooks.Dictionary:
    """Looked up by what it's made of (and any other names, and what it's for: "Enemies"), even misspelt, then by
    what it says, searched in modern spelling ("wyfe" is found by "wife")."""
    return oldbooks.Dictionary(secrets, names=lambda s: [s["name"], *s.get("also", [])],
                               text=lambda s: oldbooks.modern_spelling(f"{title(s)}. {s['text']}"), close_first=True)


DICTIONARY = dictionary(SECRETS)


def url(secret: dict) -> str:
    """The scan of the printed book, open at the secret's page."""
    return links.archive_page(SCAN, secret["page"], secret.get("highlight"))


def secret_embed(secret: dict, others: int = 0) -> discord.Embed:
    return oldbooks.passage_embed({**secret, "title": title(secret)}, others, emoji=EMOJI, colour=COLOUR,
                                  link=url(secret), footer=f"{SOURCE}, {part(secret)}",
                                  more="There are more where that came from: ask again ({n} secrets).")


def secrets_embed(what: str | None) -> discord.Embed:
    """A secret about what was typed, or (nothing typed) any."""
    return oldbooks.one_passage(DICTIONARY, what, secret_embed, emoji=EMOJI, colour=COLOUR,
                                nothing="No secret about that here. Try enemies, love, fire, invisible, "
                                        "dogs, prophecy, or a stone (amethyst, the lodestone).")


@commands.hybrid_command(name="secrets", aliases=["albertus"],
                         description="The Boke of Secretes (1560): medieval magic from herbs, stones and beasts.")
@app_commands.describe(what="What it's for or made of (enemies, invisible, fire, amethyst, owl...). Empty: random")
async def secrets(ctx: commands.Context, *, what: str | None = None):
    """A secret from The Boke of Secretes of Albertus Magnus (1560): the magic of herbs, stones and beasts, and the
    marvels of the world. Not really by Albertus (a medieval book that borrowed his name), and none of it works,
    which is the charm: a lodestone under your wife's head to learn if she's faithful, marigold and a wolf's tooth
    so nobody can speak against you, a lamp that makes whoever holds it fart. Give what you're after (enemies,
    invisible, fire, prophecy, dogs) or what it's made of (amethyst, owl, mistletoe; these autocomplete). Ask again
    for another. On its own: any secret. It's in the book's own 1560 spelling, and links to the page in the printed
    book. Typed, `!albertus` works too. Only the harmless magic is in it: nothing you could make and be hurt by."""
    await ctx.send(embed=secrets_embed(what))


@secrets.autocomplete("what")
async def what_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


OLD_BOOK = oldbooks.OldBook(SOURCE, EMOJI, "secrets", random=lambda: secrets_embed(None),
                            find=lambda topic: DICTIONARY.look_up(topic, close_first=False), title=title,
                            link=url)



async def setup(bot: commands.Bot):
    bot.add_command(secrets)
