"""/hammeredofwitches: a witch-finding tip from the Malleus Maleficarum (1486), in Montague Summers' 1928 translation.

The tips in ktdi/lib/malleus.json were picked by hand from archive.org's copy of the 1928 edition (public domain):
witch lore and how-to-spot-one advice, with OCR slips corrected against the page. The book's torture, execution and
child-harm passages are deliberately left out; tests/test_malleus.py checks nothing like them creeps back in.
"""

import json
import random
from pathlib import Path

import discord
from discord.ext import commands

HELP_CATEGORY = "🎲 Fun"
DATA = Path(__file__).resolve().parent.parent / "lib" / "malleus.json"
BOOK = "bf-1569-a-2-i-5-1928"
SOURCE = "Malleus Maleficarum (1486), tr. Montague Summers (1928)"

tips: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))


def page_url(leaf: int) -> str:
    return f"https://archive.org/details/{BOOK}/page/n{leaf}/mode/1up"


def tip_embed(tip: dict) -> discord.Embed:
    embed = discord.Embed(title="🧹 Witch-finding tip", description=f"> {discord.utils.escape_markdown(tip['text'])}",
                          color=discord.Color.dark_purple())
    embed.set_footer(text=SOURCE)
    embed.url = page_url(tip["leaf"])  # The title links to the page in the 1928 book.
    return embed


# The Malleus Maleficarum is "the Hammer of Witches", and reads like someone hammered wrote it.
@commands.hybrid_command(name="hammeredofwitches",
                         description="A witch-finding tip from the Hammer of Witches (Malleus Maleficarum, 1486).")
async def hammeredofwitches(ctx: commands.Context):
    await ctx.send(embed=tip_embed(random.choice(tips)))


async def setup(bot: commands.Bot):
    bot.add_command(hammeredofwitches)
