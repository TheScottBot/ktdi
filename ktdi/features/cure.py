"""/cure <ailment>: Nicholas Culpeper's remedy for whatever ails you, from his Complete Herbal (1653).

ktdi/lib/cure.py works out which ailment was meant (synonyms, any word order, typos: no AI); ktdi/lib/cures.json has
the herbal's sentences for each, built by ktdi/tools/cure_build.py. Nothing matching gets All-heal, which Culpeper
named for exactly this situation.

/plant <name> goes the other way: a herb, by any of Culpeper's names for it or its Latin name (ktdi/lib/herb_latin.json,
checked by hand), and everything on /cure's list he says it's good for.
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

PLANETS = {"Saturn": "♄", "Jupiter": "♃", "Mars": "♂", "Venus": "♀", "Mercury": "☿", "the Sun": "☉", "the Moon": "☽"}

data = json.loads(DATA.read_text(encoding="utf-8"))
herb_entries = lookup.herb_index(data["herbs"])
herb_titles = [herb["name"] for herb in data["herbs"]]
all_herb_names = list(dict.fromkeys(name for _, name, _ in herb_entries))
herb_remedies: dict[str, list[dict]] = {}
for _remedies in data["remedies"].values():
    for _remedy in _remedies:
        herb_remedies.setdefault(_remedy["herb"], []).append(_remedy)


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


def plant_embed(query: str) -> discord.Embed:
    match = lookup.find_herb(query, herb_entries)
    if match is None:
        shown = discord.utils.escape_markdown(" ".join(query.split())[:80])
        return discord.Embed(title=f"🌿 {shown}"[:256], color=discord.Color.dark_green(),
                             description=f"Culpeper never wrote about *{shown}*, not by that name anyway.")
    herb = match.herb
    lines = [f"*{herb['latin']}*"] if herb["latin"] else []
    if herb["planet"]:
        lines.append(f"{PLANETS[herb['planet']]} Governed by {herb['planet']}")
    in_title = " ".join(lookup.words(herb["name"]))
    others = [a for a in herb["aliases"] if " ".join(lookup.words(a)) not in in_title]
    if others:
        lines.append(f"Also called {', '.join(others)}")
    if herb["treats"]:
        lines.append(f"\n**Good for:** {', '.join(herb['treats'])}")
        lines.append(f"> {remedy_text(random.choice(herb_remedies[herb['name']]))}")
    else:
        lines.append("\nNothing on /cure's list, it turns out.")
    embed = discord.Embed(title=f"🌿 {herb['name']}"[:256], url=SOURCE_URL, color=discord.Color.dark_green(),
                          description="\n".join(lines)[:4096])
    embed.set_footer(text=SOURCE)
    return embed


@commands.hybrid_command(name="plant", description="What Culpeper's 1653 herbal says a plant cures.")
@app_commands.describe(name="A plant: any common name (ground ivy, piss-a-beds) or its Latin one (Glechoma hederacea)")
async def plant(ctx: commands.Context, *, name: str):
    await ctx.send(embed=plant_embed(name))


@plant.autocomplete("name")
async def plant_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    names = lookup.starting_first(current, all_herb_names) if current.strip() else herb_titles[:25]
    return [app_commands.Choice(name=name[:100], value=name[:100]) for name in names]


async def setup(bot: commands.Bot):
    bot.add_command(cure)
    bot.add_command(plant)
