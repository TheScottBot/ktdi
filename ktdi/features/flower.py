"""/flowermeaning [flower or meaning]: what a flower meant in Henrietta Dumont's The Language of Flowers (1851; public
domain, Project Gutenberg), when the Victorians sent messages in bouquets: a pansy is "Think of me", basil "Hate".

The flowers are in ktdi/lib/flowers.json, built by ktdi/tools/flower_build.py from a hand-read allowlist: about 270,
each with its meanings, the book's chapter of prose and verse for 70 of them, and one of the book's six
coloured plates of bouquets for a dozen. /flowermeaning <flower> is its meaning; /flowermeaning <meaning> ("love",
"grief") is a flower that means it, with the others that do named; on its own, any flower. The meanings are Dumont's:
other books of the day give others, and the footer says so.
"""

import json
import random
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "🌿 Hearth & herbs"
DATA = Path(__file__).resolve().parent.parent / "lib" / "flowers.json"
BOOK = 71779  # Project Gutenberg
PAGE = links.gutenberg(BOOK)
SOURCE = "Henrietta Dumont, The Language of Flowers (1851)"
NOTE = "Her meanings: other books of the day give others"
EMOJI = "🌸"
COLOUR = discord.Color.from_rgb(219, 112, 147)  # Pale violet red
OTHERS = 12  # Other flowers named when several mean what was asked

FLOWERS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["flowers"]


def meanings(flower: dict) -> str:
    return " · ".join(flower["meanings"])


def dictionary(flowers: list[dict]) -> oldbooks.Dictionary:
    """By the flower's names, even misspelt; then by what it means ("love" finds the flowers that mean love)."""
    return oldbooks.Dictionary(flowers, names=lambda f: [f["name"], *f.get("also", [])],
                               text=lambda f: f"{', '.join(f['meanings'])}. {f.get('text') or ''}", close_first=True)


DICTIONARY = dictionary(FLOWERS)


def url(flower: dict) -> str:
    """The flower's chapter (by its heading's anchor, or its opening words if the heading has none), or, if it has
    no chapter, the dictionary of flowers."""
    if flower.get("anchor"):
        return f"{PAGE}#{flower['anchor']}"
    return links.gutenberg(BOOK, flower["text"].split("\n")[0].replace("_", ""))


def flower_embed(flower: dict, also: list[dict] = (), asked: str = "") -> discord.Embed:
    text = f"**{oldbooks.escape(meanings(flower))}**"
    if flower.get("text"):
        paragraphs = [oldbooks.escape(p) for p in flower["text"].split("\n\n")]
        text += "\n\n" + oldbooks.fit(paragraphs, oldbooks.LONGEST - len(text))
    embed = discord.Embed(title=f"{EMOJI} {oldbooks.escape(flower['name'])}"[:256], url=url(flower),
                          description=text[:4096], color=COLOUR)
    if flower.get("plate"):
        plate = flower["plate"]
        embed.set_image(url=plate["url"])
        embed.add_field(name=f"In a bouquet: {', '.join(plate['flowers'])}", value=f"*{plate['message']}*",
                        inline=False)
    if also:
        names = " · ".join(oldbooks.escape(f["name"]) for f in random.sample(also, min(OTHERS, len(also))))
        more = f" ({len(also)} in all)" if len(also) > OTHERS else ""
        embed.add_field(name=f"Also meaning “{oldbooks.shown_typed(asked)}”{more}",
                        value=oldbooks.clip(names, 1024), inline=False)
    embed.set_footer(text=f"{SOURCE}. {NOTE}.")
    return embed


def flowermeaning_embed(asked: str | None) -> discord.Embed:
    """A flower by name; a flower meaning what was asked, with the others that do; or (nothing asked) any."""
    if not asked or not asked.strip():
        return flower_embed(random.choice(DICTIONARY.entries))
    found = DICTIONARY.look_up(asked)
    if not found:
        return discord.Embed(title=f"{EMOJI} {oldbooks.shown_typed(asked)}", color=COLOUR,
                             description=oldbooks.not_here("No flower for that here. Try a flower (rose, pansy, "
                                                           "basil) or what you want to say (love, grief, hope)."))
    if found.kind == "uses":  # A meaning: one flower that means it, and the others
        flower = random.choice(found.entries)
        return flower_embed(flower, [f for f in found.entries if f is not flower], asked)
    return flower_embed(found.entries[0])


@commands.hybrid_command(name="flowermeaning", aliases=["flower", "floriography"],
                         description="What a flower means in the Victorian language of flowers (1851), "
                                     "or the other way round.")
@app_commands.describe(flower="A flower (rose, pansy, basil...) or a meaning (love, grief, hope...). Empty: any")
async def flowermeaning(ctx: commands.Context, *, flower: str | None = None):
    """What a flower meant in the Victorian language of flowers, from Henrietta Dumont's The Language of Flowers
    (1851), when people sent messages in bouquets: a pansy is "Think of me", basil "Hate", an asphodel "My regrets
    follow you to the grave". Give a flower (rose, pansy, basil) for its meaning, with the book's prose and verse on
    it if it has a chapter and its coloured plate if it's in one; the names autocomplete. Or give a meaning (love,
    grief, hope, jealousy) for a flower that says it, with the others that do. On its own: any flower. They're
    Dumont's meanings: other books of the day gave others. Typed, `!flower` and `!floriography` work too."""
    await ctx.send(embed=flowermeaning_embed(flower))


@flowermeaning.autocomplete("flower")
async def flower_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


OLD_BOOK = oldbooks.OldBook(SOURCE, EMOJI, "flowermeaning", random=lambda: flowermeaning_embed(None),
                            find=lambda topic: DICTIONARY.look_up(topic, close_first=False), title=lambda f: f["name"],
                            link=url, text=lambda f: f"{meanings(f)}. {f.get('text') or ''}",
                            shelves=("folklore",))


async def setup(bot: commands.Bot):
    bot.add_command(flowermeaning)
