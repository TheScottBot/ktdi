"""/herbal: a random box from the grids of a 1531 herbal (Tacuini sanitatis), in all its machine-translated glory.

The cells were read by archive.org's OCR (badly: it's blackletter) and translated by Google Translate (worse), once,
by ktdi/tools/herbal_build.py, into ktdi/lib/herbal.json. Each post shows the translation, what the OCR thought the
Latin said, and the original cell, cropped from archive.org's scan.
"""

import json
import random
from pathlib import Path

import discord
from discord.ext import commands

HELP_CATEGORY = "🎲 Fun"
DATA = Path(__file__).resolve().parent.parent / "lib" / "herbal.json"
BOOK = "bub_gb_9lIU1a_-ddAC"
TITLE = "Tacuini sanitatis (1531)"
CROP_PADDING = 12  # pixels around the cell, so the crop doesn't clip the letters


def load_entries() -> list[dict]:
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


entries = load_entries()


def crop_url(page: int, box: list[int]) -> str:
    """The cell, cut out of archive.org's page image (its IIIF image server)."""
    left, top, right, bottom = box
    left, top = max(left - CROP_PADDING, 0), max(top - CROP_PADDING, 0)
    width, height = right + CROP_PADDING - left, bottom + CROP_PADDING - top
    image = f"{BOOK}%2F{BOOK}_jp2.zip%2F{BOOK}_jp2%2F{BOOK}_{page:04d}.jp2"
    return f"https://iiif.archive.org/image/iiif/3/{image}/{left},{top},{width},{height}/max/0/default.jpg"


def page_url(page: int) -> str:
    return f"https://archive.org/details/{BOOK}/page/n{page}/mode/1up"


def herbal_embed(entry: dict) -> discord.Embed:
    embed = discord.Embed(
        description=f"## {discord.utils.escape_markdown(entry['english'])}\n"
                    f"-# The scanner read: {discord.utils.escape_markdown(entry['latin'])}",
        color=discord.Color.dark_gold(),
    )
    embed.set_author(name=f"📜 {TITLE}, page {entry['page'] + 1}", url=page_url(entry["page"]))
    embed.set_image(url=crop_url(entry["page"], entry["box"]))
    return embed


@commands.hybrid_command(name="herbal", description="Wisdom from a 1531 herbal, as translated by a machine.")
async def herbal(ctx: commands.Context):
    if not entries:
        await ctx.send("The herbal hasn't been translated yet. See the README: Herbal.", ephemeral=True)
        return
    await ctx.send(embed=herbal_embed(random.choice(entries)))


async def setup(bot: commands.Bot):
    bot.add_command(herbal)
