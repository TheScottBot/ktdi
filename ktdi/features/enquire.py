"""/enquire [anything]: the Victorian answer to it, from Enquire Within Upon Everything (1856; public domain), the
book that was the internet before the internet: how to light a candle, play écarté, mend a chair, choose a mackerel,
or speak like a Londoner who has corrected his defects.

The hints are in ktdi/lib/enquire.json, built by ktdi/tools/enquire_build.py from a hand-read allowlist (with the
medical, poisoning and chemistry topics left out whole: /cure has the remedies). /enquire on its own is a random
hint; /enquire <anything> finds one about it (any word order, small typos), and says if there are more.
"""

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import links

HELP_CATEGORY = "📚 Words & wisdom"
DATA = Path(__file__).resolve().parent.parent / "lib" / "enquire.json"
SOURCE = "Enquire Within Upon Everything (1856)"
BOOK = 10766  # Project Gutenberg
COLOUR = discord.Color.teal()

HINTS: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["entries"]


def dictionary(hints: list[dict]) -> oldbooks.Dictionary:
    # Hints whose title or opening is about it ("candles") before ones that mention it in passing.
    return oldbooks.Dictionary(hints, names=lambda h: [h["title"]], text=lambda h: f"{h['title']}. {h['text']}")


DICTIONARY = dictionary(HINTS)


escape = oldbooks.escape


def url(hint: dict) -> str:
    """The book, scrolled to the hint: its number and title head it on the page ("31. In Season in January"), and
    the number makes it unique. A title the fragment can't start with its number (accents: "118. Ecarté") falls
    back on the hint's first line."""
    heading = f"{hint['number']}. {hint['title']}"
    if links.fragment_text(heading, least=2).startswith(f"{hint['number']}. "):
        return links.gutenberg(BOOK, heading, least=2)
    return links.gutenberg(BOOK, hint["text"].split("\n")[0])


def hint_embed(hint: dict, others: int = 0) -> discord.Embed:
    paragraphs = []
    for paragraph in hint["text"].split("\n\n"):  # A table or verse keeps its lines, as a block
        paragraphs.append(f"```\n{paragraph}\n```" if "\n" in paragraph else escape(paragraph))
    text = oldbooks.fit(paragraphs, oldbooks.LONGEST)
    embed = discord.Embed(title=f"🔎 {escape(hint['title'])}"[:256], url=url(hint),
                          description=text[:4096], color=COLOUR)
    more = f". There's more on that: ask again ({others + 1} hints)." if others else ""
    embed.set_footer(text=f"{SOURCE}{more}")
    return embed


def enquire_embed(query: str | None) -> discord.Embed:
    """A hint on what was asked, or (nothing asked) any hint."""
    found = DICTIONARY.one_of(query)
    if not found:
        return discord.Embed(title=f"🔎 {oldbooks.shown_typed(query)}", color=COLOUR,
                             description="Enquire Within, despite the name, has nothing on that. Try something "
                                         "plainer (candles, mackerel, chess, whist, a nightcap).")
    return hint_embed(*found)


@commands.hybrid_command(name="enquire", aliases=["enquirewithin", "ewue"],
                         description="The Victorian answer to anything, from Enquire Within (1856). Or a random hint.")
@app_commands.describe(anything="What you want to know (candles, mackerel, whist, ink stains...). Empty: random")
async def enquire(ctx: commands.Context, *, anything: str | None = None):
    """The Victorian answer to anything, from Enquire Within Upon Everything (1856): how to light a candle, choose a
    mackerel, play whist or fold a nightcap. If the book has several hints on it, you get one and it says how many
    more. On its own: a random hint."""
    await ctx.send(embed=enquire_embed(anything))


@enquire.autocomplete("anything")
async def anything_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return DICTIONARY.autocomplete(current)


OLD_BOOK = oldbooks.OldBook(SOURCE, "🔎", "enquire", random=lambda: enquire_embed(None),
                            find=lambda topic: DICTIONARY.look_up(topic), link=url)



async def setup(bot: commands.Bot):
    bot.add_command(enquire)
