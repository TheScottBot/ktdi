import os
import random
import sqlite3
import sys
from collections import defaultdict, deque
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent

# Run with --dev (e.g. "python bot.py --dev") to use the dev bot's settings in .env.dev.
ENV_FILE = ".env.dev" if "--dev" in sys.argv else ".env"
load_dotenv(BASE_DIR / ENV_FILE)

SPRAY_GIF_URL = "https://klipy.com/gifs/spray-bottle-3"
SPRAY_EMOJI = "💦"
LOOT_GIF_URL = "https://klipy.com/gifs/perception-check-tom-cardy"
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
# Comma-separated server IDs to register slash commands to (GUILD_ID also accepted).
GUILD_IDS = [int(g) for g in (os.getenv("GUILD_IDS") or os.getenv("GUILD_ID") or "").replace(" ", "").split(",") if g]
# Relative paths are resolved next to bot.py.
DB_PATH = str(BASE_DIR / os.getenv("DB_PATH", "ktdi.db"))
# Optional role given to each server's biggest briber. Skipped on servers without a role by this name.
BRIBER_ROLE_NAME = os.getenv("BRIBER_ROLE_NAME", "Champion Briber")

BLAME_LINES = [
    "This is {user}'s fault.",
    "After a thorough investigation, the committee blames {user}.",
    "{user} did this. Everyone saw it.",
    "Sources confirm: {user}.",
    "Not sure what happened, but it was definitely {user}.",
    "{user}, explain yourself.",
]

BRIBE_LINES = [
    "💰 {briber} slipped the committee **{amount}**. On review, this is actually {blamer}'s fault.",
    "💰 After receiving **{amount}** from {briber}, new evidence points to {blamer}.",
    "💰 {briber} paid **{amount}**. The committee now blames {blamer}. Justice is served.",
]

# The /linux target (our Linux hater). Override with LINUX_HATER_ID in .env.
LINUX_HATER_ID = os.getenv("LINUX_HATER_ID") or "000000000000000000"

LINUX_LINES = [
    "{user}, what're your opinions on Linux?",
    "{user}, how much do you hate Linux? Scale of 1 to 10, and 10 isn't high enough.",
    "{user}, quick question: is Linux the worst thing ever made, or just top three?",
    "{user}, if Linux were a person, what would you say to it?",
    "{user}, how many times this week has Linux personally wronged you?",
    "{user}, describe your relationship with Linux in one word. Keep it PG.",
    "{user}, someone just said \"it's the year of the Linux desktop\". Thoughts?",
    "{user}, would you rather use Linux for a week or step on Lego for a week?",
    "{user}, on a scale from \"mildly annoyed\" to \"burn it all down\", where does Linux sit today?",
    "{user}, what's your favourite thing about Linux? Trick question, we know the answer.",
    "{user}, how do you feel when someone says \"just compile it from source\"?",
    "{user}, if you had to explain your hatred of Linux to a child, how would you do it?",
    "{user}, we're taking a poll: how much do you hate Linux right now?",
    "{user}, Linux says hi. Would you like to say anything back?",
]

# Recent message authors per channel, used to pick someone to blame.
recent_speakers: dict[int, deque[int]] = defaultdict(lambda: deque(maxlen=50))

# Most recent blame per channel: channel_id -> (blamer_id, blamed_id).
last_blame: dict[int, tuple[int, int]] = {}


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
db.execute(
    """
    CREATE TABLE IF NOT EXISTS bribes (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        count    INTEGER NOT NULL DEFAULT 0,
        total    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """
)
db.execute(
    """
    CREATE TABLE IF NOT EXISTS briber_role_holders (
        guild_id INTEGER PRIMARY KEY,
        user_id  INTEGER NOT NULL
    )
    """
)
db.commit()


def record_bribe(guild_id: int, user_id: int, amount: int) -> None:
    db.execute(
        """
        INSERT INTO bribes (guild_id, user_id, count, total) VALUES (?, ?, 1, ?)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET count = count + 1, total = total + excluded.total
        """,
        (guild_id, user_id, amount),
    )
    db.commit()


def get_bribe_stats(guild_id: int, user_id: int) -> tuple[int, int]:
    row = db.execute(
        "SELECT count, total FROM bribes WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
    ).fetchone()
    return row if row else (0, 0)


def get_top_briber(guild_id: int) -> int | None:
    row = db.execute(
        "SELECT user_id FROM bribes WHERE guild_id = ? ORDER BY total DESC, user_id LIMIT 1", (guild_id,)
    ).fetchone()
    return row[0] if row else None


def get_briber_role_holder(guild_id: int) -> int | None:
    row = db.execute("SELECT user_id FROM briber_role_holders WHERE guild_id = ?", (guild_id,)).fetchone()
    return row[0] if row else None


def set_briber_role_holder(guild_id: int, user_id: int) -> None:
    db.execute(
        "INSERT INTO briber_role_holders (guild_id, user_id) VALUES (?, ?)"
        " ON CONFLICT (guild_id) DO UPDATE SET user_id = excluded.user_id",
        (guild_id, user_id),
    )
    db.commit()


async def get_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
    try:
        return guild.get_member(user_id) or await guild.fetch_member(user_id)
    except discord.HTTPException:
        return None  # Left the server, or couldn't look them up.


async def update_briber_role(guild: discord.Guild) -> None:
    """Move the briber role to the server's biggest briber. Does nothing if the role or permission is missing."""
    role = discord.utils.get(guild.roles, name=BRIBER_ROLE_NAME)
    top_id = get_top_briber(guild.id)
    if role is None or top_id is None:
        return
    previous_id = get_briber_role_holder(guild.id)
    try:
        if previous_id and previous_id != top_id:
            previous = await get_member(guild, previous_id)
            if previous and role in previous.roles:
                await previous.remove_roles(role, reason="No longer the biggest briber")
        top = await get_member(guild, top_id)
        if top and role not in top.roles:
            await top.add_roles(role, reason="Biggest briber")
        set_briber_role_holder(guild.id, top_id)
    except discord.HTTPException as error:
        # Usually missing Manage Roles, or the role sits above the bot's own role.
        print(f"Couldn't update {BRIBER_ROLE_NAME!r} role in {guild.name}: {error}", flush=True)


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
        if GUILD_IDS:
            # Server-only slash commands update instantly; global ones can take a while to reach clients.
            for guild_id in GUILD_IDS:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                print(f"Synced {len(synced)} slash commands to server {guild_id}", flush=True)
            # Remove any old global copies so commands don't show up twice.
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
        else:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} global slash commands", flush=True)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Tell people when they typed a command wrong instead of failing silently.
        if isinstance(error, (commands.UserInputError, commands.NoPrivateMessage)):
            await ctx.send(str(error), ephemeral=True)
        elif not isinstance(error, commands.CommandNotFound):
            await super().on_command_error(ctx, error)


bot = KTDIBot()


@bot.hybrid_command(name="spray", description="Spray the degenerate.")
@commands.guild_only()
async def spray(ctx: commands.Context, target: discord.Member | None = None):
    if target is None:
        await ctx.send(SPRAY_GIF_URL)
        return
    record_spray(ctx.guild.id, target.id)
    await ctx.send(f"{target.mention} {SPRAY_GIF_URL}")


@bot.hybrid_command(name="loot", description="Declare that you're looting the body.")
async def loot(ctx: commands.Context):
    await ctx.send(LOOT_GIF_URL)


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


@bot.hybrid_command(name="rapsheet", description="See someone's sprays and bribes.")
@commands.guild_only()
async def rapsheet(ctx: commands.Context, user: discord.Member | None = None):
    user = user or ctx.author
    sprays = get_spray_count(ctx.guild.id, user.id)
    bribes, bribe_total = get_bribe_stats(ctx.guild.id, user.id)
    if sprays == 0 and bribes == 0:
        await ctx.send(f"📋 {user.display_name} has a clean record. Suspicious.")
        return
    lines = [f"📋 **Rap sheet: {user.display_name}**"]
    if sprays:
        lines.append(f"Sprayed {plural(sprays, 'time')}.")
    if bribes:
        lines.append(f"Bribed the committee {plural(bribes, 'time')} (${bribe_total:,} total).")
        if get_top_briber(ctx.guild.id) == user.id:
            lines.append("👑 Biggest briber in the server.")
    await ctx.send("\n".join(lines))


@bot.hybrid_command(name="blame", description="Blame someone who's been talking recently.")
@commands.guild_only()
async def blame(ctx: commands.Context, *, reason: str | None = None):
    candidates = set(recent_speakers[ctx.channel.id]) or {ctx.author.id}
    blamed_id = random.choice(list(candidates))
    last_blame[ctx.channel.id] = (ctx.author.id, blamed_id)
    line = random.choice(BLAME_LINES).format(user=f"<@{blamed_id}>")
    if reason:
        line = f"**{reason}**\n{line}"
    await ctx.send(line)


@bot.hybrid_command(name="bribe", description="Blamed? Pay to put the blame back on whoever blamed you.")
@commands.guild_only()
async def bribe(ctx: commands.Context, amount: commands.Range[int, 1, 1_000_000_000_000]):
    blame_record = last_blame.get(ctx.channel.id)
    if blame_record is None:
        await ctx.send("Nobody's been blamed here. Save your money.", ephemeral=True)
        return
    blamer_id, blamed_id = blame_record
    if ctx.author.id != blamed_id:
        await ctx.send(f"You're not the one being blamed, <@{blamed_id}> is. Nice try.", ephemeral=True)
        return
    if blamer_id == blamed_id:
        await ctx.send("You blamed yourself. There's nobody to pass it to.", ephemeral=True)
        return
    record_bribe(ctx.guild.id, ctx.author.id, amount)
    # Flip the blame, so the original blamer can counter-bribe.
    last_blame[ctx.channel.id] = (blamed_id, blamer_id)
    await ctx.send(
        random.choice(BRIBE_LINES).format(briber=ctx.author.mention, blamer=f"<@{blamer_id}>", amount=f"${amount:,}")
    )
    await update_briber_role(ctx.guild)


@bot.hybrid_command(name="linux", description="Ask our resident Linux hater how he's feeling about Linux.")
async def linux(ctx: commands.Context):
    await ctx.send(random.choice(LINUX_LINES).format(user=f"<@{LINUX_HATER_ID}>"))


@bot.hybrid_command(name="help",description="List everything this bot can do.")
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
    # flush so the line shows up in journalctl straight away under systemd.
    print(f"Logged in as {bot.user} (ID: {bot.user.id}), prefix: {COMMAND_PREFIX!r}", flush=True)


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit(f"DISCORD_TOKEN is not set. Copy .env.example to {ENV_FILE} and add your token.")
    bot.run(token)


if __name__ == "__main__":
    main()
