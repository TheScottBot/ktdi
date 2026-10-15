"""/melancholy [topic]: Robert Burton's The Anatomy of Melancholy (1621, public domain): a passage of his gloomy,
learned, digressive wisdom on love, study, bad air, sleep, poverty, jealousy, idleness, or anything else that might
make a person melancholy (which, by his account, is everything).

The passages are excerpts picked by hand, word for word, into ktdi/lib/melancholy.json (ktdi/tools/melancholy_build.py
checks each against the book). /melancholy on its own is a random one; /melancholy <topic> finds one in a part of the
book about it (Burton's own subsection titles: "Bad Air, a cause of Melancholy"), or one that mentions it.
"""

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "📚 Words & wisdom"
DATA = Path(__file__).resolve().parent.parent / "lib" / "melancholy.json"
SOURCE = "Burton, The Anatomy of Melancholy (1621)"
BOOK = 10800  # Project Gutenberg
COLOUR = discord.Color.dark_purple()

PASSAGES: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["passages"]


def dictionary(passages: list[dict]) -> oldbooks.Dictionary:
    return oldbooks.titled(passages)


DICTIONARY = dictionary(PASSAGES)


def url(passage: dict) -> str:
    """The book, scrolled to the excerpt (by its anchor: words with no footnote mark among them on the page)."""
    return links.gutenberg(BOOK, passage.get("anchor") or passage["text"])


def passage_embed(passage: dict, others: int = 0) -> discord.Embed:
    return oldbooks.passage_embed(passage, others, emoji="🖤", colour=COLOUR, link=url(passage), footer=SOURCE,
                                  more="He has more to say on that: ask again ({n} passages).")


def melancholy_embed(topic: str | None) -> discord.Embed:
    """A passage on the topic, or (no topic) any."""
    return oldbooks.one_passage(DICTIONARY, topic, passage_embed, emoji="🖤", colour=COLOUR,
                                nothing="Nothing from Burton on that here. Try "
                                        "love, study, sleep, idleness, jealousy, poverty or bad air.")


@commands.hybrid_command(name="melancholy", aliases=["burton", "gloom"],
                         description="Burton's gloomy wisdom (1621) on love, study, sleep, poverty... Or a random bit.")
@app_commands.describe(topic="What to be melancholy about (love, study, sleep, jealousy...). Empty: anything")
async def melancholy(ctx: commands.Context, *, topic: str | None = None):
    """A passage of Robert Burton's The Anatomy of Melancholy (1621) on whatever's getting you down: love, study, sleep,
    jealousy, poverty, tobacco. It comes from a part of the book about it (his own titles autocomplete), or one that
    mentions it; ask again for another. On its own: anything."""
    await ctx.send(embed=melancholy_embed(topic))


@melancholy.autocomplete("topic")
async def topic_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


OLD_BOOK = oldbooks.OldBook(SOURCE, "🖤", "melancholy", random=lambda: melancholy_embed(None),
                            find=lambda topic: DICTIONARY.look_up(topic), link=url)



async def setup(bot: commands.Bot):
    bot.add_command(melancholy)
