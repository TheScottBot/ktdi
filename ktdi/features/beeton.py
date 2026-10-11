"""/beeton: Mrs Beeton's Book of Household Management (1861, public domain). Her recipes really work.

/beeton recipe <dish> finds a recipe by name, or one using an ingredient ("eels"), with the others that use it
listed; with no dish it's a random one ("what's for dinner, 1861"). Each shows her ingredients, method, time, cost
(in 1861 money), when it's in season and how many it serves, and often her aside on where the food comes from.
/beeton advice [topic] is her advice on running a house: early rising, servants, dinner parties, wills. (Not the
nursery or the doctor: /cure has that.) Typed, !beeton <dish> is a recipe.

The data is ktdi/lib/beeton.json, built by ktdi/tools/beeton_build.py from a hand-read allowlist.
"""

import json
import random
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import oldbooks
from ktdi.lib import fuzzy, links

HELP_CATEGORY = "📜 Old books"
DATA = Path(__file__).resolve().parent.parent / "lib" / "beeton.json"
SOURCE = "Mrs Beeton's Book of Household Management (1861)"
BOOK = 10136  # Project Gutenberg
COLOUR = discord.Color.from_rgb(150, 75, 0)  # Gravy
OTHERS = 12  # Other recipes named when an ingredient turns up in several
ASIDE = 400  # Her aside, clipped

ENTRIES: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["entries"]


def recipes(entries: list[dict]) -> oldbooks.Dictionary:
    # Searching a recipe's name and ingredients: "eels" finds what's made with them.
    return oldbooks.Dictionary([e for e in entries if e["kind"] == "recipe"], names=lambda e: [e["name"]],
                               text=lambda e: f"{e['name']}. {e['ingredients']}", meaning_first=False)


def advice(entries: list[dict]) -> oldbooks.Dictionary:
    # Passages that open on the topic ("EARLY RISING IS ONE OF...") before ones that only mention it.
    return oldbooks.Dictionary([e for e in entries if e["kind"] == "advice"], names=lambda e: [e["name"]],
                               text=lambda e: e["text"], meaning_first=True)


RECIPES, ADVICE = recipes(ENTRIES), advice(ENTRIES)


escape = oldbooks.escape


def url(entry: dict) -> str:
    """The book, scrolled to the recipe's method or the advice (their first words; ingredients have fractions in them,
    which the page sets differently)."""
    return links.gutenberg(BOOK, entry["method"] if entry["kind"] == "recipe" else entry["text"])


def particulars(entry: dict) -> str:
    """"⏱️ 3 hours · 💷 2s. 3d. per quart · 🍽️ for 8 persons · 📅 all the year"."""
    parts = [("⏱️", entry.get("time")), ("💷", entry.get("cost")), ("🍽️", entry.get("serves")),
             ("📅", entry.get("seasonable"))]
    return " · ".join(f"{icon} {escape(text)}" for icon, text in parts if text)


def recipe_embed(entry: dict, also: list[dict] = (), typed: str = "") -> discord.Embed:
    subtitle = f"*{escape(entry['subtitle'])}*\n\n" if entry.get("subtitle") else ""
    method = oldbooks.fit([escape(p) for p in entry["method"].split("\n\n")], oldbooks.LONGEST - 500)
    lines = [particulars(entry)]
    if entry.get("aside"):
        lines.append(f"-# 📖 {escape(oldbooks.clip(entry['aside'], ASIDE))}")
    description = f"{subtitle}{method}\n\n" + "\n".join(line for line in lines if line)
    embed = discord.Embed(title=f"🍽️ {escape(entry['name'])}"[:256], url=url(entry), description=description[:4096],
                          color=COLOUR)
    embed.add_field(name="Ingredients", value=oldbooks.clip(escape(entry["ingredients"]), 1024), inline=False)
    if also:
        names = " · ".join(escape(e["name"]) for e in random.sample(also, min(OTHERS, len(also))))
        more = f" ({len(also)} in all)" if len(also) > OTHERS else ""
        embed.add_field(name=f"Also with “{oldbooks.shown_typed(typed)}”{more}", value=oldbooks.clip(names, 1024),
                        inline=False)
    embed.set_footer(text=SOURCE)
    return embed


def advice_embed(entry: dict, others: int = 0) -> discord.Embed:
    text = oldbooks.fit([escape(p) for p in entry["text"].split("\n\n")], oldbooks.LONGEST)
    embed = discord.Embed(title=f"🏠 {escape(entry['name'])}"[:256], url=url(entry), description=text, color=COLOUR)
    more = f". She has more to say on that: ask again ({others + 1} passages)." if others else ""
    embed.set_footer(text=f"{SOURCE}{more}")
    return embed


def nothing(typed: str, message: str) -> discord.Embed:
    return discord.Embed(title=f"🍽️ {oldbooks.shown_typed(typed)}", description=message, color=COLOUR)


def recipe(query: str | None) -> discord.Embed:
    """A recipe by name, one using an ingredient (with the others listed), or a random one."""
    if not query or not fuzzy.words(query):
        return recipe_embed(random.choice(RECIPES.entries))
    found = RECIPES.look_up(query)
    if not found:
        return nothing(query, "Mrs Beeton has no recipe for that. Try a dish or an ingredient (soup, eels, "
                              "pudding, mutton).")
    if found.kind == "uses":  # An ingredient: one of the recipes with it, and the rest named
        chosen = random.choice(found.entries)
        return recipe_embed(chosen, [e for e in found.entries if e is not chosen], query)
    return recipe_embed(random.choice(found.entries))  # Several versions of a dish: any of them


def household(query: str | None) -> discord.Embed:
    """Her advice on something, or (nothing typed) any of it."""
    found = ADVICE.one_of(query)
    if not found:
        return nothing(query, "Mrs Beeton is silent on that, which is unlike her. Try servants, dinner, early "
                              "rising, washing, a will.")
    return advice_embed(*found)


# /beeton recipe [dish] and /beeton advice [topic]. Typed, !beeton <dish> is a recipe, and !beeton on its own a random
# one. (Discord won't run a bare /beeton once it has subcommands, hence /beeton recipe with no dish.)
@commands.hybrid_group(name="beeton", aliases=["mrsbeeton"], fallback="recipe", invoke_without_command=True,
                       description="Mrs Beeton (1861): a recipe by dish or ingredient, or a random one.")
@app_commands.describe(dish="A dish or ingredient (almond soup, eels, pudding...). Empty: random")
async def beeton(ctx: commands.Context, *, dish: str | None = None):
    await ctx.send(embed=recipe(dish))


@beeton.command(name="advice", description="Mrs Beeton's advice on running a house (1861).")
@app_commands.describe(topic="What about (servants, dinner, early rising, washing...). Empty: any")
async def beeton_advice(ctx: commands.Context, *, topic: str | None = None):
    await ctx.send(embed=household(topic))


@beeton.autocomplete("dish")
async def dish_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return RECIPES.autocomplete(current)


async def setup(bot: commands.Bot):
    bot.add_command(beeton)
