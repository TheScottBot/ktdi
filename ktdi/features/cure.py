"""/cure <ailment>: Nicholas Culpeper's remedy for whatever ails you, from his Complete Herbal (1653).

ktdi/lib/cure.py works out which ailment was meant (synonyms, any word order, typos: no AI); ktdi/lib/cures.json has
the herbal's sentences for each, built by ktdi/tools/cure_build.py. Nothing matching gets All-heal, which Culpeper
named for exactly this situation.
"""

import json
import random
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi.lib import cure as lookup

HELP_CATEGORY = "🎲 Fun"
DATA = Path(__file__).resolve().parent.parent / "lib" / "cures.json"
SOURCE = "Culpeper's Complete Herbal (1653)"
SOURCE_URL = "https://www.gutenberg.org/ebooks/49513"

data = json.loads(DATA.read_text(encoding="utf-8"))


def remedy_text(remedy: dict) -> str:
    """The sentence, with the words that matched the ailment in bold."""
    text, (start, end) = remedy["text"], remedy["match"]
    escape = discord.utils.escape_markdown
    if start == end:
        return escape(text)
    return f"{escape(text[:start])}**{escape(text[start:end])}**{escape(text[end:])}"


def cure_embed(query: str) -> discord.Embed:
    match = lookup.find(query)
    shown = discord.utils.escape_markdown(" ".join(query.split())[:80])
    embed = discord.Embed(title=f"🌿 A cure for {shown}"[:256], url=SOURCE_URL, color=discord.Color.dark_green())
    if match is None:
        remedy = random.choice(data["allheal"])
        embed.description = (f"Culpeper has never heard of *{shown}*, but swears by **{remedy['herb']}**:\n"
                              f"> {remedy_text(remedy)}")
    else:
        remedy = random.choice(data["remedies"][match.ailment.name])
        embed.description = f"**{remedy['herb']}**: {remedy_text(remedy)}"
        if lookup.words(query) != lookup.words(match.ailment.name):
            embed.description += f"\n-# Filed under: {match.ailment.name}"
    embed.set_footer(text=SOURCE)
    return embed


@commands.hybrid_command(name="cure", description="Nicholas Culpeper's 1653 remedy for whatever ails you.")
@app_commands.describe(ailment="What's wrong with you (anything: a cold, a broken heart, a missing arm...)")
async def cure(ctx: commands.Context, *, ailment: str):
    await ctx.send(embed=cure_embed(ailment))


@cure.autocomplete("ailment")
async def ailment_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=name[:100], value=name[:100]) for name in lookup.suggestions(current)]


async def setup(bot: commands.Bot):
    bot.add_command(cure)
