"""/herbal: a random box from the grids of a 1531 herbal (Tacuini sanitatis), in all its machine-translated glory,
and a dig: react ⛏️ to go one translation worse, down to bedrock.

The cells were read by archive.org's OCR (badly: it's blackletter) and translated by Google Translate (worse), once,
by ktdi/tools/herbal_build.py, into ktdi/lib/herbal.json. Each box has levels: the best guess, then the same again
round-tripped through one more language per level. Below the last level is bedrock: the Latin as the scanner read it.
Posts and how deep they've been dug are in the database (herbal_posts), so a dig carries on after a restart.
"""

import json
import random
from pathlib import Path

import discord
from discord.ext import commands

from ktdi import common, db
from ktdi.common import NO_PINGS

HELP_CATEGORY = "🎲 Fun"
DATA = Path(__file__).resolve().parent.parent / "lib" / "herbal.json"
BOOK = "bub_gb_9lIU1a_-ddAC"
TITLE = "Tacuini sanitatis (1531)"
CROP_PADDING = 12  # pixels around the cell, so the crop doesn't clip the letters
DIG = "⛏️"
LEVEL_NAMES = ["Best guess", "Worse", "Worse still", "Deeper", "Deeper still", "Deepest"]


def load_entries() -> dict[int, dict]:
    """Entries by id, each with its levels. (Older data had one "english" translation and no ids.)"""
    try:
        raw = json.loads(DATA.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {entry.get("id", number): {**entry, "levels": entry.get("levels") or [entry["english"]]}
            for number, entry in enumerate(raw, start=1)}


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


def herbal_embed(entry: dict, depth: int = 0) -> discord.Embed:
    """The box at a depth: the levels dug through so far, small, then the current one large. One past the last
    level is bedrock: the Latin as the scanner read it."""
    levels = entry["levels"]
    lines = [f"-# {LEVEL_NAMES[i]}: {discord.utils.escape_markdown(levels[i])}" for i in range(min(depth, len(levels)))]
    if depth < len(levels):
        lines.append(f"## {discord.utils.escape_markdown(levels[depth])}")
        lines.append(f"-# {'React' if depth == 0 else f'{DIG} {depth} deep. React'} {DIG} to dig deeper.")
    else:
        lines.append(f"## 🪨 Bedrock\nThe scanner read: *{discord.utils.escape_markdown(entry['latin'])}*")
    embed = discord.Embed(description="\n".join(lines), color=discord.Color.dark_gold())
    embed.set_author(name=f"📜 {TITLE}, page {entry['page'] + 1}", url=page_url(entry["page"]))
    embed.set_image(url=crop_url(entry["page"], entry["box"]))
    return embed


@commands.hybrid_command(name="herbal", description="Wisdom from a 1531 herbal, as translated by a machine. ⛏️ to dig.")
async def herbal(ctx: commands.Context):
    if not entries:
        await ctx.send("The herbal hasn't been translated yet. See the README: Herbal.", ephemeral=True)
        return
    entry_id = random.choice(list(entries))
    message = await ctx.send(embed=herbal_embed(entries[entry_id]), allowed_mentions=NO_PINGS)
    db.conn.execute("INSERT OR REPLACE INTO herbal_posts (message_id, guild_id, entry_id, depth) VALUES (?, ?, ?, 0)",
                    (message.id, ctx.guild.id if ctx.guild else None, entry_id))
    db.conn.commit()
    try:
        await message.add_reaction(DIG)  # So the pickaxe is right there to click.
    except discord.HTTPException:
        pass  # No Add Reactions permission: people can still add it themselves.


def _is_dig(emoji) -> bool:
    return str(emoji).replace("️", "") == DIG.replace("️", "")


async def dig(payload: discord.RawReactionActionEvent):
    """⛏️ on a /herbal post: one translation worse, until bedrock."""
    if not _is_dig(payload.emoji) or payload.user_id == common.bot.user.id:
        return
    row = db.conn.execute("SELECT entry_id, depth FROM herbal_posts WHERE message_id = ?",
                          (payload.message_id,)).fetchone()
    entry = entries.get(row[0]) if row else None
    channel = common.bot.get_channel(payload.channel_id)
    if entry is None or channel is None:
        return
    message = channel.get_partial_message(payload.message_id)
    depth = row[1]
    if depth < len(entry["levels"]):  # Already at bedrock: nothing further down.
        depth += 1
        db.conn.execute("UPDATE herbal_posts SET depth = ? WHERE message_id = ?", (depth, payload.message_id))
        db.conn.commit()
        await message.edit(embed=herbal_embed(entry, depth))
    try:
        await message.remove_reaction(payload.emoji, discord.Object(id=payload.user_id))  # Ready to dig again.
    except discord.HTTPException:
        pass  # Needs Manage Messages; without it, un-react and react again to dig.


async def setup(bot: commands.Bot):
    bot.add_command(herbal)
    bot.add_listener(dig, "on_raw_reaction_add")
