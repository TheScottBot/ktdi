import os
import random
import sqlite3
from collections import defaultdict, deque
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

SPRAY_GIF_URL = "https://klipy.com/gifs/spray-bottle-3"
SPRAY_EMOJI = "💦"
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
DB_PATH = os.getenv("DB_PATH", str(Path(__file__).parent / "ktdi.db"))

BLAME_LINES = [
    "This is {user}'s fault.",
    "After a thorough investigation, the committee blames {user}.",
    "{user} did this. Everyone saw it.",
    "Sources confirm: {user}.",
    "Not sure what happened, but it was definitely {user}.",
    "{user}, explain yourself.",
]

# Recent message authors per channel, used to pick someone to blame.
recent_speakers: dict[int, deque[int]] = defaultdict(lambda: deque(maxlen=50))


db = sqlite3.connect(DB_PATH)
db.execute(
    """
    CREATE TABLE IF NOT EXISTS sprays (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        count    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """
)
db.commit()


def record_spray(guild_id: int, user_id: int) -> int:
    db.execute(
        """
        INSERT INTO sprays (guild_id, user_id, count) VALUES (?, ?, 1)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET count = count + 1
        """,
        (guild_id, user_id),
    )
    db.commit()
    return get_spray_count(guild_id, user_id)


def get_spray_count(guild_id: int, user_id: int) -> int:
    row = db.execute(
        "SELECT count FROM sprays WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
    ).fetchone()
    return row[0] if row else 0


class KTDIBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        # Needed to read "<prefix>spray" from messages. Must also be enabled in the Developer Portal.
        intents.message_content = True
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

    async def setup_hook(self):
        await self.tree.sync()


bot = KTDIBot()


@bot.hybrid_command(name="spray", description="Spray the degenerate.")
@commands.guild_only()
async def spray(ctx: commands.Context, target: discord.Member | None = None):
    if target is None:
        await ctx.send(SPRAY_GIF_URL)
        return
    record_spray(ctx.guild.id, target.id)
    await ctx.send(f"{target.mention} {SPRAY_GIF_URL}")


@bot.hybrid_command(name="rapsheet", description="See how many times someone has been sprayed.")
@commands.guild_only()
async def rapsheet(ctx: commands.Context, user: discord.Member | None = None):
    user = user or ctx.author
    count = get_spray_count(ctx.guild.id, user.id)
    if count == 0:
        await ctx.send(f"📋 {user.display_name} has a clean record. Suspicious.")
    else:
        times = "time" if count == 1 else "times"
        await ctx.send(f"📋 **Rap sheet: {user.display_name}**\nSprayed {count} {times}.")


@bot.hybrid_command(name="blame", description="Blame someone who's been talking recently.")
@commands.guild_only()
async def blame(ctx: commands.Context, *, reason: str | None = None):
    candidates = set(recent_speakers[ctx.channel.id]) or {ctx.author.id}
    line = random.choice(BLAME_LINES).format(user=f"<@{random.choice(list(candidates))}>")
    if reason:
        line = f"**{reason}**\n{line}"
    await ctx.send(line)


@bot.hybrid_command(name="help", description="List everything this bot can do.")
async def help_command(ctx: commands.Context):
    embed = discord.Embed(
        title="Keep The Degenerates Inline",
        description=f"Use `/command` or `{COMMAND_PREFIX}command`.",
        color=discord.Color.blurple(),
    )
    for command in sorted(bot.commands, key=lambda c: c.name):
        embed.add_field(
            name=f"/{command.name} {command.signature}".strip(),
            value=command.description or "No description.",
            inline=False,
        )
    embed.add_field(
        name=f"React {SPRAY_EMOJI}",
        value="Sprays whoever sent the message and adds to their rap sheet.",
        inline=False,
    )
    await ctx.send(embed=embed)


@bot.listen()
async def on_message(message: discord.Message):
    if message.guild and not message.author.bot:
        recent_speakers[message.channel.id].append(message.author.id)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # Reacting 💦 to a message sprays whoever sent it.
    if str(payload.emoji) != SPRAY_EMOJI or payload.user_id == bot.user.id:
        return
    channel = bot.get_channel(payload.channel_id)
    if channel is None:
        return
    target = ""
    if payload.message_author_id:
        target = f"<@{payload.message_author_id}> "
        if payload.guild_id:
            record_spray(payload.guild_id, payload.message_author_id)
    await channel.send(f"{target}{SPRAY_GIF_URL}")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id}), prefix: {COMMAND_PREFIX!r}")


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and add your token.")
    bot.run(token)


if __name__ == "__main__":
    main()
