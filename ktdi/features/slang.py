"""/vulgartongue: Regency slang from Grose's 1811 Dictionary of the Vulgar Tongue ("Buckish Slang, University Wit, and
Pickpocket Eloquence"). Handy for NPC dialogue; handier for calling your friends a Captain Queernabs.

/vulgartongue lookup <word> looks a word up (any word order, small typos), or failing that finds the entries whose definitions
use it ("drunk" gets every 1811 way of saying drunk); with no word, it's a random entry. /vulgartongue insult @someone
insults them with a random one. The data is ktdi/lib/slang.json, built by ktdi/tools/slang_build.py, with every slur and anything
that punches down (sexist, racist, xenophobic, homophobic, about sex, mocking disability) taken out.
"""

import json
import random
import re
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ktdi.lib import cure as lookup

HELP_CATEGORY = "📜 Old books"
DATA = Path(__file__).resolve().parent.parent / "lib" / "slang.json"
SOURCE = "Grose's Dictionary of the Vulgar Tongue (1811)"
SOURCE_URL = "https://www.gutenberg.org/ebooks/5402"
SHOWN = 8  # Entries listed when a word turns up in several definitions.
LINE_LENGTH = 140

ENTRIES: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["entries"]
INSULTS = [entry for entry in ENTRIES if entry["insult"]]
PHRASES = [entry for entry in ENTRIES if not entry["insult"]]  # What a random one comes from: never an insult


def display_word(word: str) -> str:
    """"CAPTAIN QUEERNABS" -> "Captain Queernabs"; "ADDLE PATE, or ADDLE PLOT" keeps its "or"."""
    shown = re.sub(r"\b(Or|To|A|An|Of|The|And|In)\b", lambda m: m.group(1).lower(), word.title())
    return discord.utils.escape_markdown(shown[0].upper() + shown[1:].replace("'S", "'s").replace("’S", "’s"))


def headwords(entry: dict) -> list[str]:
    """Every word an entry is filed under: "ADDLE PATE, or ADDLE PLOT" is both."""
    return [part.strip(" ,") for part in re.split(r",? or ", entry["word"], flags=re.IGNORECASE) if part.strip(" ,")]


INDEX = [(entry, name, tuple(lookup.words(name))) for entry in ENTRIES for name in headwords(entry)
         if lookup.words(name)]
ALL_WORDS = sorted({display_word(name) for _, name, _ in INDEX})


def in_definitions(query: str, leave_out: dict | None = None) -> list[dict]:
    """Entries whose definitions use every word typed ("drunk": BOSKY, CUT, FOXED...). Ones that mean it (it's in
    the first part of the definition) come first; ones that only mention it in passing only if nothing means it."""
    typed = lookup.words(query)
    if not typed:
        return []
    patterns = [re.compile(rf"\b{re.escape(word)}\w*", re.IGNORECASE) for word in typed]
    found = [e for e in ENTRIES if e is not leave_out and all(p.search(e["text"]) for p in patterns)]
    meaning = [e for e in found if all(p.search(re.split(r"[.;]", e["text"], maxsplit=1)[0]) for p in patterns)]
    return meaning or found


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:text.rfind(" ", 0, limit - 1)].rstrip(",;:") + "…"


def entry_embed(entry: dict, query: str | None = None) -> discord.Embed:
    embed = discord.Embed(title=f"📖 {display_word(entry['word'])}"[:256], url=SOURCE_URL,
                          description=discord.utils.escape_markdown(entry["text"])[:4096],
                          color=discord.Color.dark_teal())
    others = in_definitions(query, leave_out=entry) if query else []
    if others:  # "drunk" is a word in the dictionary, and there are plenty of other ways to say it.
        names = " · ".join(display_word(e["word"]) for e in random.sample(others, min(12, len(others))))
        typed = discord.utils.escape_markdown(" ".join(query.split())[:60])
        embed.add_field(name=f"Other ways to say “{typed}”", value=clip(names, 1024), inline=False)
    embed.set_footer(text=SOURCE)
    return embed


def slang_embed(query: str | None) -> discord.Embed:
    """A word looked up, the entries that use it, or (nothing typed) a random phrase that isn't an insult."""
    if not query or not lookup.words(query):
        return entry_embed(random.choice(PHRASES))
    match = lookup.best_match(query, INDEX, spelling=0.85)
    if match and match[2]:  # It's a word in the dictionary.
        return entry_embed(match[0], query)
    found = in_definitions(query)
    if found:
        shown = random.sample(found, min(SHOWN, len(found)))
        lines = [clip(f"**{display_word(e['word'])}**: {discord.utils.escape_markdown(e['text'])}", LINE_LENGTH)
                 for e in shown]
        typed = discord.utils.escape_markdown(" ".join(query.split())[:60])
        embed = discord.Embed(title=f"📖 “{typed}”, in 1811"[:256], url=SOURCE_URL, description="\n".join(lines),
                              color=discord.Color.dark_teal())
        more = f". Showing {len(shown)} of {len(found)}: ask again for others." if len(found) > len(shown) else ""
        embed.set_footer(text=f"{SOURCE}{more}")
        return embed
    if match:  # Nothing uses it, but a word in the dictionary looks like it.
        return entry_embed(match[0])
    typed = discord.utils.escape_markdown(" ".join(query.split())[:60])
    return discord.Embed(title=f"📖 {typed}", color=discord.Color.dark_teal(),
                         description="Grose never wrote that down. Try a plainer word (drunk, fool, money, run away).")


def insult_text(insulter: discord.abc.User, person: discord.abc.User, entry: dict) -> str:
    return (f"🎩 {insulter.mention} has insulted {person.mention}, in the words of 1811:\n"
            f"# {display_word(entry['word'])}!\n> {discord.utils.escape_markdown(entry['text'])}\n-# {SOURCE}")


# /vulgartongue lookup [word], /vulgartongue random and /vulgartongue insult <person>. Typed, !vulgartongue <word> (or
# !vt, or !slang) looks it up, and on its own it's a random phrase. (Discord won't run a bare /vulgartongue once it has
# subcommands, hence /vulgartongue random.)
@commands.hybrid_group(name="vulgartongue", aliases=["vt", "slang"], fallback="lookup", invoke_without_command=True,
                       description="1811 slang: look a word up, find the slang for one, or get a random one.")
@app_commands.describe(word="A word to look up, or a plain one (drunk, fool...) to find the slang for. Empty: random")
async def slang(ctx: commands.Context, *, word: str | None = None):
    await ctx.send(embed=slang_embed(word))


@slang.command(name="random", description="A random phrase from 1811 (never an insult).")
async def slang_random(ctx: commands.Context):
    await ctx.send(embed=slang_embed(None))


@slang.command(name="insult", description="Insult someone, in the words of 1811.")
@app_commands.describe(person="Who's getting it")
async def slang_insult(ctx: commands.Context, person: discord.Member):
    entry = random.choice(INSULTS)
    await ctx.send(insult_text(ctx.author, person, entry),
                   allowed_mentions=discord.AllowedMentions(users=[person], everyone=False, roles=False))
    if ctx.guild:  # Insults are hostile acts: enough of them is a diplomatic incident (/wars).
        from ktdi.features import wars
        await wars.hostility(ctx.guild.id, ctx.channel.id, ctx.author.id, person.id, "insult",
                             detail=display_word(entry["word"]))


@slang.autocomplete("word")
async def word_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    names = lookup.starting_first(current, ALL_WORDS) if current.strip() else random.sample(ALL_WORDS, 25)
    return [app_commands.Choice(name=name[:100], value=name[:100]) for name in names]


async def setup(bot: commands.Bot):
    bot.add_command(slang)
