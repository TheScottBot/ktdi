"""/pseudodoxia [topic]: Sir Thomas Browne's Pseudodoxia Epidemica, or "Vulgar Errors" (1646, public domain): a whole
book of what everyone wrongly believed (that a badger's legs are shorter on one side, that elephants have no joints,
that a kingfisher hung by the beak shows which way the wind blows), each one solemnly examined.

The chapters are in ktdi/lib/pseudodoxia.json, built by ktdi/tools/pseudodoxia_build.py from a hand-read allowlist.
/pseudodoxia on its own is a random chapter; /pseudodoxia <topic> finds one about it (his chapter titles: "Of the
Badger"), or one that mentions it, and says if there are more. Each links to its place in the book.
"""

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "🔮 Old oddities"
DATA = Path(__file__).resolve().parent.parent / "lib" / "pseudodoxia.json"
SOURCE = "Sir Thomas Browne, Pseudodoxia Epidemica (1646)"
COLOUR = discord.Color.from_rgb(112, 84, 62)  # Old leather

CHAPTERS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["chapters"]


def dictionary(chapters: list[dict]) -> oldbooks.Dictionary:
    return oldbooks.titled(chapters)


DICTIONARY = dictionary(CHAPTERS)


def url(chapter: dict) -> str:
    """The volume it's in, scrolled to the chapter's opening."""
    return links.gutenberg(chapter["volume"], chapter.get("anchor") or chapter["text"])


def chapter_embed(chapter: dict, others: int = 0) -> discord.Embed:
    return oldbooks.passage_embed(chapter, others, emoji="🧐", colour=COLOUR, link=url(chapter),
                                  footer=f"{SOURCE}, book {chapter['book']}, chapter {chapter['chapter']}",
                                  more="He examines more on that: ask again ({n} chapters).")


def pseudodoxia_embed(topic: str | None) -> discord.Embed:
    """A chapter on the topic, or (no topic) any."""
    return oldbooks.one_passage(DICTIONARY, topic, chapter_embed, emoji="🧐", colour=COLOUR,
                                nothing="Browne never got round to examining that one. Try badgers, elephants, "
                                        "griffins, the phoenix, unicorns, or the salamander.")


@commands.hybrid_command(name="pseudodoxia", aliases=["vulgarerrors", "browne"],
                         description="Browne's Vulgar Errors (1646): what everyone wrongly believed, solemnly examined.")
@app_commands.describe(topic="A creature, thing or belief (badgers, elephants, the phoenix...). Empty: random")
async def pseudodoxia(ctx: commands.Context, *, topic: str | None = None):
    """A chapter of Sir Thomas Browne's Pseudodoxia Epidemica, or "Vulgar Errors" (1646): a whole book of what everyone
    wrongly believed (that a badger's legs are shorter on one side, that elephants have no joints, that a kingfisher
    hung by its beak shows which way the wind blows), each one stated and then solemnly taken apart. Give a topic
    (badgers, griffins, the phoenix, unicorns) for a chapter about it; his chapter titles autocomplete. Ask again for
    another on the same topic. On its own: any chapter. Typed, `!vulgarerrors` and `!browne` work too."""
    await ctx.send(embed=pseudodoxia_embed(topic))


@pseudodoxia.autocomplete("topic")
async def topic_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


async def setup(bot: commands.Bot):
    bot.add_command(pseudodoxia)
