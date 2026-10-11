"""/etiquette: what an 1860s etiquette manual says to do, for any situation, today's included ("texting", "D&D").

The rules are hand-picked, word for word, from Routledge's Manual of Etiquette and Cecil Hartley's The Gentlemen's Book
of Etiquette (both 1860s, public domain, via Project Gutenberg) into ktdi/lib/etiquette.json, each tagged with its
topics (dinner, letters, games...). ktdi/lib/etiquette.py files what people type under those topics, no AI.

/etiquette gentleman, gentlewoman and gentlethem [situation] each give a rule for it from their own pool: rules written
for gentlemen, for ladies, or for nobody in particular (any rule that says "he", "she", "gentleman" or "lady" is
gendered, whatever it was tagged). No situation: any rule from the pool; nothing fitting: the nearest, with a shrug.
/etiquette remind @someone reminds them of one, publicly.
"""

import json
import random
import re
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi.lib import etiquette as situations

HELP_CATEGORY = "📜 Old books"
DATA = Path(__file__).resolve().parent.parent / "lib" / "etiquette.json"
BOOKS = {
    "routledge": ("Routledge's Manual of Etiquette (1860s)", "https://www.gutenberg.org/ebooks/12426"),
    "hartley": ("Hartley, The Gentlemen's Book of Etiquette (1860)", "https://www.gutenberg.org/ebooks/39293"),
}
FOR = {"ladies": "For ladies", "gentlemen": "For gentlemen"}
# Words that make a rule about a gentleman or a lady, whatever it was tagged: gentlethem only gets rules without them.
GENTLEMEN_WORDS = re.compile(r"\b(?:gentlem[ae]n|man|men|he|him|his|himself|sir|husband|son|brother|beau)\b", re.I)
LADIES_WORDS = re.compile(r"\b(?:lad(?:y|ies)|wom[ae]n|she|her|hers|herself|madam|wife|daughter|sister|girl)\b", re.I)

RULES: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))


def audience(rule: dict) -> str:
    """Who a rule's for: "gentlemen", "ladies", or "anyone" (gentlethem). A rule tagged for nobody that talks about
    gentlemen or ladies goes to them."""
    if rule.get("for") in FOR:
        return rule["for"]
    gentlemen, ladies = GENTLEMEN_WORDS.search(rule["text"]), LADIES_WORDS.search(rule["text"])
    if rule["book"] == "hartley" and (gentlemen or ladies):
        return "gentlemen"  # Hartley's whole book is addressed to gentlemen, even when it talks about ladies
    if gentlemen and not ladies:
        return "gentlemen"
    if ladies and not gentlemen:
        return "ladies"
    return "both" if gentlemen else "anyone"  # "both": about gentlemen and ladies, so not for gentlethem either


def pool(who: str) -> list[dict]:
    return [rule for rule in RULES if audience(rule) == who]

SILENT = [
    "The manuals are silent on *{situation}*. In the circumstances, the committee offers this:",
    "No Victorian ever found themselves in *{situation}*. The nearest guidance:",
    "*{situation}* had not been invented. The committee suggests applying this:",
]


def rule_for(situation: str | None, rules: list[dict]) -> tuple[dict, str | None, bool]:
    """A rule from these for the situation: (rule, the topic it came from, whether that topic was found). No
    situation: any of them."""
    if not situation or not situation.strip():
        return random.choice(rules), None, True
    found = situations.find_topic(situation)
    if found:
        topic, _ = found
        fitting = [rule for rule in rules if topic in rule["topics"]]
        if fitting:
            return random.choice(fitting), topic, True
    return random.choice(rules), None, False


def quoted(rule: dict) -> str:
    return "\n".join(f"> {line}" for line in discord.utils.escape_markdown(rule["text"]).split("\n"))


# Who each subcommand is for: (the pool, the title's emoji and word).
WHO = {"gentleman": ("gentlemen", "🎩", "Gentleman"), "gentlewoman": ("ladies", "👒", "Gentlewoman"),
       "gentlethem": ("anyone", "🧐", "Gentlethem")}


def advice_embed(situation: str | None, who: str) -> discord.Embed:
    rules_for, emoji, word = WHO[who]
    rule, topic, found = rule_for(situation, pool(rules_for))
    title, url = BOOKS[rule["book"]]
    shown = discord.utils.escape_markdown(" ".join((situation or "").split())[:80])
    heading = f"{emoji} {word}'s etiquette: {shown}" if shown else f"{emoji} {word}'s etiquette"
    intro = "" if found else random.choice(SILENT).format(situation=shown) + "\n"
    description = intro + quoted(rule)
    if topic:
        description += f"\n-# Filed under: {topic}"
    embed = discord.Embed(title=heading[:256], url=url, description=description[:4096],
                          color=discord.Color.dark_magenta())
    embed.set_footer(text=title)
    return embed


def reminder_text(reminder: discord.abc.User, person: discord.abc.User) -> str:
    rule = random.choice(RULES)
    return (f"🎩 {reminder.mention} reminds {person.mention} of the rules:\n{quoted(rule)}\n"
            f"-# {BOOKS[rule['book']][0]}")


# /etiquette gentleman, gentlewoman, gentlethem [situation], and /etiquette remind <person>. Typed, !etiquette
# <situation> on its own is gentlethem's.
@commands.hybrid_group(name="etiquette", invoke_without_command=True,
                       description="What an 1860s etiquette manual says to do, for any situation.")
async def etiquette_group(ctx: commands.Context, *, situation: str | None = None):
    await ctx.send(embed=advice_embed(situation, "gentlethem"))


SITUATION = "What's happening (texting, dinner, D&D, the pub...). Empty: any rule"


@etiquette_group.command(name="gentleman", aliases=["gentlemen"], description="An 1860s rule for gentlemen.")
@app_commands.describe(situation=SITUATION)
async def etiquette_gentleman(ctx: commands.Context, *, situation: str | None = None):
    await ctx.send(embed=advice_embed(situation, "gentleman"))


@etiquette_group.command(name="gentlewoman", aliases=["gentlewomen"], description="An 1860s rule for ladies.")
@app_commands.describe(situation=SITUATION)
async def etiquette_gentlewoman(ctx: commands.Context, *, situation: str | None = None):
    await ctx.send(embed=advice_embed(situation, "gentlewoman"))


@etiquette_group.command(name="gentlethem", description="An 1860s rule for anyone at all.")
@app_commands.describe(situation=SITUATION)
async def etiquette_gentlethem(ctx: commands.Context, *, situation: str | None = None):
    await ctx.send(embed=advice_embed(situation, "gentlethem"))


@etiquette_group.command(name="remind", description="Remind someone of the rules, in 1860s terms.")
@app_commands.describe(person="Who needs reminding")
async def etiquette_remind(ctx: commands.Context, person: discord.Member):
    await ctx.send(reminder_text(ctx.author, person),
                   allowed_mentions=discord.AllowedMentions(users=[person], everyone=False, roles=False))


async def situation_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=name[:100], value=name[:100]) for name in situations.suggestions(current)]


for _command in (etiquette_gentleman, etiquette_gentlewoman, etiquette_gentlethem):
    _command.autocomplete("situation")(situation_autocomplete)


async def setup(bot: commands.Bot):
    bot.add_command(etiquette_group)
