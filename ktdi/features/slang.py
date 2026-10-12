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

from ktdi import oldbooks
from ktdi.lib import fuzzy, links

HELP_CATEGORY = "📚 Words & wisdom"
DATA = Path(__file__).resolve().parent.parent / "lib" / "slang.json"
SOURCE = "Grose's Dictionary of the Vulgar Tongue (1811)"
BOOK = 5402  # On Project Gutenberg
COLOUR = discord.Color.dark_teal()

ENTRIES: list[dict] = json.loads(DATA.read_text(encoding="utf-8"))["entries"]
INSULTS = [entry for entry in ENTRIES if entry["insult"]]
PHRASES = [entry for entry in ENTRIES if not entry["insult"]]  # What a random one comes from: never an insult


def shown_word(word: str) -> str:
    """"CAPTAIN QUEERNABS" -> "Captain Queernabs"; "ADDLE PATE, or ADDLE PLOT" keeps its "or"."""
    shown = re.sub(r"\b(Or|To|A|An|Of|The|And|In)\b", lambda m: m.group(1).lower(), word.title())
    return shown[0].upper() + shown[1:].replace("'S", "'s").replace("’S", "’s")


def display_word(word: str) -> str:
    """shown_word, made safe for Discord."""
    return discord.utils.escape_markdown(shown_word(word))


def headwords(entry: dict) -> list[str]:
    """Every word an entry is filed under: "ADDLE PATE, or ADDLE PLOT" is both."""
    return [part.strip(" ,") for part in re.split(r",? or ", entry["word"], flags=re.IGNORECASE) if part.strip(" ,")]


DICTIONARY = oldbooks.Dictionary(ENTRIES, names=headwords, text=lambda entry: entry["text"], shown_name=display_word)


def url(entry: dict) -> str:
    # Its headword leads, as in the book, so even a two-word entry ("BENE. Good.") can be found and highlighted.
    return links.gutenberg(BOOK, f"{entry['word']}. {entry['text']}", least=2)


def entry_embed(entry: dict, query: str | None = None) -> discord.Embed:
    embed = discord.Embed(title=f"📖 {display_word(entry['word'])}"[:256], url=url(entry),
                          description=discord.utils.escape_markdown(entry["text"])[:4096], color=COLOUR)
    others = DICTIONARY.uses(query, leave_out=entry) if query else []
    if others:  # "drunk" is a word in the dictionary, and there are plenty of other ways to say it.
        names = " · ".join(display_word(e["word"]) for e in random.sample(others, min(12, len(others))))
        embed.add_field(name=f"Other ways to say “{oldbooks.shown_typed(query)}”", value=oldbooks.clip(names, 1024),
                        inline=False)
    embed.set_footer(text=SOURCE)
    return embed


def slang_embed(query: str | None) -> discord.Embed:
    """A word looked up, the entries that use it, or (nothing typed) a random phrase that isn't an insult."""
    if not query or not fuzzy.words(query):
        return entry_embed(random.choice(PHRASES))
    found = DICTIONARY.look_up(query)
    if found and found.kind == "exact":  # It's a word in the dictionary.
        return entry_embed(found.entries[0], query)
    if found and found.kind == "uses":
        return oldbooks.uses_embed(
            found.entries, title=f"📖 “{oldbooks.shown_typed(query)}”, in 1811", name=lambda e: display_word(e["word"]),
            query=query, text=lambda e: e["text"], link=url, source=SOURCE, colour=COLOUR)
    if found:  # Nothing uses it, but a word in the dictionary looks like it.
        return entry_embed(found.entries[0])
    return discord.Embed(title=f"📖 {oldbooks.shown_typed(query)}", color=COLOUR,
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
    """Regency slang from Grose's Dictionary of the Vulgar Tongue (1811). `/vulgartongue lookup <word>` looks a word up,
    or for a plain word (drunk, coward) finds the slang for it. `/vulgartongue random`: a random phrase.
    `/vulgartongue insult @someone` insults them in the words of 1811 (enough insults flying and it's a diplomatic
    incident: `/wars`)."""
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
    return DICTIONARY.autocomplete(current)


OLD_BOOK = oldbooks.OldBook(SOURCE, "📖", "vulgartongue", random=lambda: slang_embed(None),
                            find=lambda topic: DICTIONARY.look_up(topic), title=lambda e: shown_word(e["word"]),
                            link=url)



async def setup(bot: commands.Bot):
    bot.add_command(slang)
