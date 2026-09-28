import io
import logging
import os
import random
import sqlite3
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import abm
import library

BASE_DIR = Path(__file__).parent

# Run with --dev (e.g. "python bot.py --dev") to use the dev bot's settings in .env.dev.
ENV_FILE = ".env.dev" if "--dev" in sys.argv else ".env"
load_dotenv(BASE_DIR / ENV_FILE)

SPRAY_GIF_URL = "https://klipy.com/gifs/spray-bottle-3"
SPRAY_EMOJI = "💦"
LOOT_GIF_URL = "https://klipy.com/gifs/perception-check-tom-cardy"
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")


def parse_ids(*env_names: str) -> list[int]:
    """Comma-separated IDs from the first of these env vars that is set. Skips (and warns about) typos."""
    raw = next((os.getenv(name) for name in env_names if os.getenv(name)), "")
    ids = []
    for item in raw.replace(" ", "").split(","):
        if item.isdigit():
            ids.append(int(item))
        elif item:
            logging.getLogger("ktdi").warning("Ignoring %r in %s: server IDs are numbers only.", item, env_names[0])
    return ids


# Comma-separated server IDs to register slash commands to (GUILD_ID also accepted).
GUILD_IDS = parse_ids("GUILD_IDS", "GUILD_ID")
# Calibre-Web library for /books. The commands only work in BOOKS_GUILD_IDS, and only if CALIBRE_URL is set.
BOOKS_GUILD_IDS = parse_ids("BOOKS_GUILD_IDS")
CALIBRE_URL = os.getenv("CALIBRE_URL")
BOOK_FORMATS = [f for f in (os.getenv("BOOK_FORMATS") or "epub,kepub,azw3,mobi,pdf,cbz").replace(" ", "").split(",") if f]
calibre = (
    library.CalibreWeb(CALIBRE_URL, os.getenv("CALIBRE_USERNAME", ""), os.getenv("CALIBRE_PASSWORD", ""), BOOK_FORMATS)
    if CALIBRE_URL else None
)
# Relative paths are resolved next to bot.py.
DB_PATH = str(BASE_DIR / os.getenv("DB_PATH", "ktdi.db"))
# Rolling log file (relative to bot.py). Rotates at LOG_MAX_BYTES, keeping LOG_BACKUPS old files.
LOG_FILE = BASE_DIR / os.getenv("LOG_FILE", "logs/ktdi-dev.log" if "--dev" in sys.argv else "logs/ktdi.log")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 1_000_000))
LOG_BACKUPS = int(os.getenv("LOG_BACKUPS", 5))
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
db.execute(
    """
    CREATE TABLE IF NOT EXISTS quotes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,  -- who said it
        text       TEXT NOT NULL,
        context    TEXT,
        added_by   INTEGER NOT NULL,
        channel_id INTEGER,
        message_id INTEGER,           -- the original message, if it was saved from one
        created_at TEXT NOT NULL      -- ISO 8601, UTC
    )
    """
)
db.commit()


log = logging.getLogger("ktdi")


def setup_logging() -> None:
    """Log to the terminal (so journalctl still works) and to a rolling log file."""
    formatter = logging.Formatter("[{asctime}] [{levelname:<7}] {name}: {message}", "%Y-%m-%d %H:%M:%S", style="{")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)
    # The log file is best-effort: if it can't be opened, keep running with terminal/journal logging only.
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8")
    except OSError as error:
        log.warning("Couldn't open log file %s, logging to terminal only: %s", LOG_FILE, error)
        return
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


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
                log.info("[%s] Took %r from %s", guild.name, BRIBER_ROLE_NAME, previous)
        top = await get_member(guild, top_id)
        if top and role not in top.roles:
            await top.add_roles(role, reason="Biggest briber")
            log.info("[%s] Gave %r to %s", guild.name, BRIBER_ROLE_NAME, top)
        set_briber_role_holder(guild.id, top_id)
    except discord.HTTPException as error:
        # Usually missing Manage Roles, or the role sits above the bot's own role.
        log.warning("[%s] Couldn't update %r role: %s", guild.name, BRIBER_ROLE_NAME, error)


QUOTE_MAX_LENGTH = 1000
QUOTE_CONTEXT_MAX_LENGTH = 200
QUOTE_COLUMNS = "id, guild_id, user_id, text, context, added_by, channel_id, message_id, created_at"


@dataclass
class Quote:
    id: int
    guild_id: int
    user_id: int
    text: str
    context: str | None
    added_by: int
    channel_id: int | None
    message_id: int | None
    created_at: str


def add_quote(guild_id: int, user_id: int, text: str, context: str | None, added_by: int,
              channel_id: int | None = None, message_id: int | None = None) -> int:
    cursor = db.execute(
        "INSERT INTO quotes (guild_id, user_id, text, context, added_by, channel_id, message_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (guild_id, user_id, text, context, added_by, channel_id, message_id,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    db.commit()
    return cursor.lastrowid


def get_quote(guild_id: int, quote_id: int) -> Quote | None:
    row = db.execute(f"SELECT {QUOTE_COLUMNS} FROM quotes WHERE guild_id = ? AND id = ?", (guild_id, quote_id)).fetchone()
    return Quote(*row) if row else None


def quote_for_message(guild_id: int, message_id: int) -> Quote | None:
    row = db.execute(f"SELECT {QUOTE_COLUMNS} FROM quotes WHERE guild_id = ? AND message_id = ?",
                     (guild_id, message_id)).fetchone()
    return Quote(*row) if row else None


def random_quote(guild_id: int, user_id: int | None = None) -> Quote | None:
    if user_id is None:
        row = db.execute(f"SELECT {QUOTE_COLUMNS} FROM quotes WHERE guild_id = ? ORDER BY RANDOM() LIMIT 1",
                         (guild_id,)).fetchone()
    else:
        row = db.execute(f"SELECT {QUOTE_COLUMNS} FROM quotes WHERE guild_id = ? AND user_id = ? ORDER BY RANDOM() LIMIT 1",
                         (guild_id, user_id)).fetchone()
    return Quote(*row) if row else None


def search_quotes(guild_id: int, text: str, limit: int = 10) -> list[Quote]:
    pattern = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = db.execute(
        f"SELECT {QUOTE_COLUMNS} FROM quotes WHERE guild_id = ? AND (text LIKE ? ESCAPE '\\' OR context LIKE ? ESCAPE '\\')"
        " ORDER BY id DESC LIMIT ?",
        (guild_id, pattern, pattern, limit),
    ).fetchall()
    return [Quote(*row) for row in rows]


def recent_quotes(guild_id: int, limit: int, user_id: int | None = None) -> list[Quote]:
    if user_id is None:
        rows = db.execute(f"SELECT {QUOTE_COLUMNS} FROM quotes WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
                          (guild_id, limit)).fetchall()
    else:
        rows = db.execute(f"SELECT {QUOTE_COLUMNS} FROM quotes WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
                          (guild_id, user_id, limit)).fetchall()
    return [Quote(*row) for row in rows]


def delete_quote(guild_id: int, quote_id: int) -> None:
    db.execute("DELETE FROM quotes WHERE guild_id = ? AND id = ?", (guild_id, quote_id))
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
        if GUILD_IDS:
            # Server-only slash commands update instantly; global ones can take a while to reach clients.
            for guild_id in GUILD_IDS:
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                if calibre is None or guild_id not in BOOKS_GUILD_IDS:
                    self.tree.remove_command("books", guild=guild)  # Don't show /books where it can't be used.
                synced = await self.tree.sync(guild=guild)
                log.info("Synced %d slash commands to server %s", len(synced), guild_id)
            # Remove any old global copies so commands don't show up twice.
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
        else:
            if calibre is None:
                self.tree.remove_command("books")  # Library not set up, so don't show /books anywhere.
            synced = await self.tree.sync()
            log.info("Synced %d global slash commands", len(synced))

    async def on_command(self, ctx: commands.Context):
        # Fires for both /commands and prefix commands.
        if is_private_command(ctx):
            return  # Library use isn't logged, so nobody's reading is tied back to them.
        if ctx.interaction:
            invocation = f"/{ctx.command.qualified_name} {describe_options(ctx.interaction.data.get('options', []))}".strip()
        else:
            invocation = ctx.message.content
        where = f"{ctx.guild.name} #{ctx.channel}" if ctx.guild else "DM"
        log.info("[%s] %s ran %r", where, ctx.author, invocation)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Tell people when they typed a command wrong instead of failing silently.
        who = "Someone" if is_private_command(ctx) else str(ctx.author)
        if isinstance(error, (commands.UserInputError, commands.NoPrivateMessage)):
            log.info("%s's %s command failed: %s", who, ctx.command, error)
            await ctx.send(str(error), ephemeral=True)
        elif isinstance(error, commands.CheckFailure):
            log.info("%s can't use %s here: %s", who, ctx.command, error)
            await ctx.send(str(error) or "You can't use that here.", ephemeral=True)
        elif not isinstance(error, commands.CommandNotFound):
            await super().on_command_error(ctx, error)


def is_private_command(ctx: commands.Context) -> bool:
    """Library commands, which are never logged with who used them or what they looked for."""
    return ctx.command is not None and (ctx.command.root_parent or ctx.command).name == "books"


def describe_options(options: list[dict]) -> str:
    """Slash command options as 'name=value', flattening subcommands like /books search."""
    parts = []
    for option in options:
        if "options" in option:
            parts.append(describe_options(option["options"]))
        elif "value" in option:
            parts.append(f"{option['name']}={option['value']}")
    return " ".join(p for p in parts if p)


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


@bot.hybrid_command(name="abm", description="Anything But Metric: convert a measurement into something absurd.")
async def abm_command(ctx: commands.Context, *, measurement: str):
    try:
        await ctx.send(abm.convert(measurement))
    except abm.ABMError as error:
        await ctx.send(str(error), ephemeral=True)


@bot.hybrid_command(name="imperial", description="Sincerely convert a metric measurement to imperial/US units.")
async def imperial_command(ctx: commands.Context, *, measurement: str):
    try:
        await ctx.send(abm.to_imperial(measurement))
    except abm.ABMError as error:
        await ctx.send(str(error), ephemeral=True)


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
    log.info("[%s] %s blamed user %s", ctx.guild.name, ctx.author, blamed_id)
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
    log.info("[%s] %s bribed $%s, blame moved to user %s", ctx.guild.name, ctx.author, f"{amount:,}", blamer_id)
    await ctx.send(
        random.choice(BRIBE_LINES).format(briber=ctx.author.mention, blamer=f"<@{blamer_id}>", amount=f"${amount:,}")
    )
    await update_briber_role(ctx.guild)


@bot.hybrid_command(name="linux", description="Ask our resident Linux hater how he's feeling about Linux.")
async def linux(ctx: commands.Context):
    await ctx.send(random.choice(LINUX_LINES).format(user=f"<@{LINUX_HATER_ID}>"))


# --- Quotes ---
# Ways in: /quote add, !quote @user text, replying to a message with !quote [@user], or right-click > Apps > Save quote.
NO_PINGS = discord.AllowedMentions.none()
MENTION_AT_START_RE = re.compile(r"^\s*<@!?(\d+)>\s*(.*)$", re.DOTALL)


@dataclass
class Reply:
    content: str | None = None
    embed: discord.Embed | None = None
    private: bool = False  # Only shown to the person who asked (slash commands only).


def quote_embed(quote: Quote) -> discord.Embed:
    description = f"“{quote.text}”\n— <@{quote.user_id}>"
    if quote.context:
        description += f"\n*{quote.context}*"
    if quote.message_id and quote.channel_id:
        description += f"\n[Original message](https://discord.com/channels/{quote.guild_id}/{quote.channel_id}/{quote.message_id})"
    embed = discord.Embed(description=description, color=discord.Color.gold(),
                          timestamp=datetime.fromisoformat(quote.created_at))
    embed.set_footer(text=f"Quote #{quote.id}")
    return embed


def split_context(text: str) -> tuple[str, str | None]:
    """'I cast fireball -- on myself' -> ('I cast fireball', 'on myself')."""
    if " -- " in f" {text} ":
        quote_text, _, context = f" {text} ".partition(" -- ")
        return quote_text.strip(), context.strip() or None
    return text.strip(), None


def save_quote(guild: discord.Guild, channel_id: int | None, added_by: discord.abc.User, said_by: int,
               text: str | None, context: str | None, source: discord.Message | None = None) -> Reply:
    text = (text or "").strip()
    context = (context or "").strip() or None
    if not text:
        return Reply("There's nothing to quote. That message has no text, so type it in: `/quote add`.", private=True)
    if len(text) > QUOTE_MAX_LENGTH:
        return Reply(f"That's a bit long for a quote (max {QUOTE_MAX_LENGTH} characters).", private=True)
    if context and len(context) > QUOTE_CONTEXT_MAX_LENGTH:
        return Reply(f"The context is too long (max {QUOTE_CONTEXT_MAX_LENGTH} characters).", private=True)
    if source:
        existing = quote_for_message(guild.id, source.id)
        if existing and existing.text == text and existing.user_id == said_by:
            return Reply(f"That's already saved as quote #{existing.id}.", private=True)
    quote_id = add_quote(guild.id, said_by, text, context, added_by.id, channel_id, source.id if source else None)
    log.info("[%s] %s saved quote #%d (said by user %s)", guild.name, added_by, quote_id, said_by)
    return Reply(f"📌 Saved quote #{quote_id}.", quote_embed(get_quote(guild.id, quote_id)))


def show_random_quote(guild: discord.Guild, user: discord.abc.User | None = None) -> Reply:
    quote = random_quote(guild.id, user.id if user else None)
    if quote is None:
        if user:
            return Reply(f"No quotes from {user.display_name} yet.", private=True)
        return Reply("No quotes saved yet. Reply to a message with `!quote`, or use `/quote add`.", private=True)
    return Reply(embed=quote_embed(quote))


def show_quote(guild: discord.Guild, number: int) -> Reply:
    quote = get_quote(guild.id, number)
    return Reply(embed=quote_embed(quote)) if quote else Reply(f"There's no quote #{number}.", private=True)


def remove_quote(guild: discord.Guild, member: discord.Member, number: int) -> Reply:
    quote = get_quote(guild.id, number)
    if quote is None:
        return Reply(f"There's no quote #{number}.", private=True)
    if member.id not in (quote.added_by, quote.user_id) and not member.guild_permissions.manage_messages:
        return Reply(f"Only whoever saved quote #{number}, the person quoted, or a moderator can delete it.", private=True)
    delete_quote(guild.id, number)
    log.info("[%s] %s deleted quote #%d", guild.name, member, number)
    return Reply(f"🗑️ Deleted quote #{number}.")


QUOTE_LIST_MAX = 15


def quote_line(quote: Quote, length: int = 80) -> str:
    """One-line summary for lists: #12 “text…” — @user · date."""
    text = quote.text if len(quote.text) <= length else quote.text[:length].rstrip() + "…"
    when = int(datetime.fromisoformat(quote.created_at).timestamp())
    return f"`#{quote.id}` “{text}” — <@{quote.user_id}> · <t:{when}:d>"


def last_quotes(guild: discord.Guild, count: int, user: discord.abc.User | None = None) -> Reply:
    count = max(1, min(count, QUOTE_LIST_MAX))
    quotes = recent_quotes(guild.id, count, user.id if user else None)
    if not quotes:
        return show_random_quote(guild, user)  # Same "no quotes yet" message.
    who = f" from {user.display_name}" if user else ""
    embed = discord.Embed(title=f"🗒️ Last {len(quotes)} quote{'s' if len(quotes) != 1 else ''}{who}",
                          description="\n".join(quote_line(q, 120) for q in quotes), color=discord.Color.gold())
    embed.set_footer(text="Show one in full with /quote show <number>.")
    return Reply(embed=embed)


def find_quotes(guild: discord.Guild, text: str) -> Reply:
    results = search_quotes(guild.id, text.strip())
    if not results:
        return Reply(f"No quotes mention “{discord.utils.escape_markdown(text)}”.", private=True)
    lines = [quote_line(q) for q in results]
    embed = discord.Embed(title=f"🔎 Quotes mentioning “{text[:100]}”", description="\n".join(lines),
                          color=discord.Color.gold())
    embed.set_footer(text="Show one with /quote show <number>." + (" Showing the 10 newest." if len(results) == 10 else ""))
    return Reply(embed=embed)


async def send_reply(ctx: commands.Context, reply: Reply) -> None:
    await ctx.send(reply.content, embed=reply.embed, allowed_mentions=NO_PINGS)


async def respond(interaction: discord.Interaction, reply: Reply) -> None:
    await interaction.response.send_message(reply.content, embed=reply.embed, ephemeral=reply.private,
                                            allowed_mentions=NO_PINGS)


async def replied_message(ctx: commands.Context) -> discord.Message | None:
    reference = ctx.message.reference
    if reference is None or reference.message_id is None:
        return None
    if isinstance(reference.resolved, discord.Message):
        return reference.resolved
    return await ctx.channel.fetch_message(reference.message_id)


# Prefix version: !quote handles replies and "@user text" itself, plus the same subcommands as /quote.
@bot.group(name="quote", description="Save and replay the things people say.", invoke_without_command=True)
@commands.guild_only()
async def quote_prefix(ctx: commands.Context, *, args: str = ""):
    match = MENTION_AT_START_RE.match(args)
    said_by = int(match.group(1)) if match else None
    text = (match.group(2) if match else args).strip()
    try:
        replied = await replied_message(ctx)
    except discord.HTTPException:
        await ctx.send("I couldn't read the message you replied to. I need the Read Message History permission here.")
        return

    if replied:
        # "!quote" or "!quote @Dave" as a reply saves that message; any text typed replaces its wording.
        quote_text, context = split_context(text)
        reply = save_quote(ctx.guild, ctx.channel.id, ctx.author, said_by or replied.author.id,
                           quote_text or replied.content, context, replied)
    elif said_by is None and text.isdigit():
        reply = show_quote(ctx.guild, int(text))
    elif text and said_by is None:
        reply = Reply(f"Who said it? Use `{COMMAND_PREFIX}quote @someone what they said`, "
                      f"or reply to their message with `{COMMAND_PREFIX}quote`.")
    elif text:
        quote_text, context = split_context(text)
        reply = save_quote(ctx.guild, ctx.channel.id, ctx.author, said_by, quote_text, context)
    else:
        # "!quote" or "!quote @Dave" on its own: a random quote.
        user = discord.utils.get(ctx.message.mentions, id=said_by) if said_by else None
        reply = show_random_quote(ctx.guild, user)
    await send_reply(ctx, reply)


@quote_prefix.command(name="add", description="Save something someone said.")
async def quote_prefix_add(ctx: commands.Context, user: discord.Member, *, text: str):
    quote_text, context = split_context(text)
    await send_reply(ctx, save_quote(ctx.guild, ctx.channel.id, ctx.author, user.id, quote_text, context))


@quote_prefix.command(name="random", description="A random quote, optionally from one person.")
async def quote_prefix_random(ctx: commands.Context, user: discord.Member | None = None):
    await send_reply(ctx, show_random_quote(ctx.guild, user))


@quote_prefix.command(name="last", description=f"The most recent quotes (default 5, max {QUOTE_LIST_MAX}), optionally from one person.")
async def quote_prefix_last(ctx: commands.Context, count: int | None = 5, user: discord.Member | None = None):
    await send_reply(ctx, last_quotes(ctx.guild, count or 5, user))


@quote_prefix.command(name="show", description="Show a quote by its number.")
async def quote_prefix_show(ctx: commands.Context, number: int):
    await send_reply(ctx, show_quote(ctx.guild, number))


@quote_prefix.command(name="search", description="Find quotes containing some text.")
async def quote_prefix_search(ctx: commands.Context, *, text: str):
    await send_reply(ctx, find_quotes(ctx.guild, text))


@quote_prefix.command(name="delete", description="Delete a quote (whoever saved it, the person quoted, or a mod).")
async def quote_prefix_delete(ctx: commands.Context, number: int):
    await send_reply(ctx, remove_quote(ctx.guild, ctx.author, number))


# Slash version.
quote_slash = app_commands.Group(name="quote", description="Save and replay the things people say.", guild_only=True)


@quote_slash.command(name="add", description="Save something someone said (great for things said in voice).")
@app_commands.describe(user="Who said it", text="What they said", context="Optional: what was going on at the time")
async def quote_slash_add(interaction: discord.Interaction, user: discord.Member,
                          text: app_commands.Range[str, 1, QUOTE_MAX_LENGTH],
                          context: app_commands.Range[str, 1, QUOTE_CONTEXT_MAX_LENGTH] | None = None):
    await respond(interaction, save_quote(interaction.guild, interaction.channel_id, interaction.user, user.id, text, context))


@quote_slash.command(name="random", description="A random quote, optionally from one person.")
async def quote_slash_random(interaction: discord.Interaction, user: discord.Member | None = None):
    await respond(interaction, show_random_quote(interaction.guild, user))


@quote_slash.command(name="last", description="The most recent quotes, optionally from one person.")
@app_commands.describe(count=f"How many (default 5, max {QUOTE_LIST_MAX})", user="Only quotes from this person")
async def quote_slash_last(interaction: discord.Interaction,
                           count: app_commands.Range[int, 1, QUOTE_LIST_MAX] = 5, user: discord.Member | None = None):
    await respond(interaction, last_quotes(interaction.guild, count, user))


@quote_slash.command(name="show", description="Show a quote by its number.")
async def quote_slash_show(interaction: discord.Interaction, number: int):
    await respond(interaction, show_quote(interaction.guild, number))


@quote_slash.command(name="search", description="Find quotes containing some text.")
async def quote_slash_search(interaction: discord.Interaction, text: str):
    await respond(interaction, find_quotes(interaction.guild, text))


@quote_slash.command(name="delete", description="Delete a quote (whoever saved it, the person quoted, or a mod).")
async def quote_slash_delete(interaction: discord.Interaction, number: int):
    await respond(interaction, remove_quote(interaction.guild, interaction.user, number))


bot.tree.add_command(quote_slash)


class SaveQuoteModal(discord.ui.Modal, title="Save quote"):
    """Opened from right-click > Apps > Save quote. Lets you fix the wording and pick who said it."""

    def __init__(self, source: discord.Message):
        super().__init__()
        self.source = source
        self.quote_text = discord.ui.TextInput(style=discord.TextStyle.paragraph, max_length=QUOTE_MAX_LENGTH,
                                               default=source.content[:QUOTE_MAX_LENGTH] or None)
        self.said_by = discord.ui.UserSelect(default_values=[discord.Object(id=source.author.id)], required=True)
        self.context = discord.ui.TextInput(required=False, max_length=QUOTE_CONTEXT_MAX_LENGTH,
                                            placeholder="e.g. mid-fight, right after rolling a nat 1")
        self.add_item(discord.ui.Label(text="Quote", component=self.quote_text))
        self.add_item(discord.ui.Label(text="Who said it?", component=self.said_by,
                                       description="Change this if someone typed out what another person said."))
        self.add_item(discord.ui.Label(text="Context (optional)", component=self.context))

    async def on_submit(self, interaction: discord.Interaction):
        said_by = self.said_by.values[0].id if self.said_by.values else self.source.author.id
        await respond(interaction, save_quote(interaction.guild, self.source.channel.id, interaction.user, said_by,
                                              self.quote_text.value, self.context.value, self.source))


@bot.tree.context_menu(name="Save quote")
@app_commands.guild_only()
async def save_quote_menu(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.send_modal(SaveQuoteModal(message))


DM_FILE_SIZE_LIMIT = 10 * 1024 * 1024  # Discord's upload limit outside boosted servers.
SEARCH_RESULTS_SHOWN = 15
# Books seen in recent searches, so /books download <id> knows their formats and sizes.
recent_books: dict[int, library.Book] = {}


def books_available(guild: discord.Guild | None) -> bool:
    return calibre is not None and guild is not None and guild.id in BOOKS_GUILD_IDS


def books_enabled():
    async def predicate(ctx: commands.Context) -> bool:
        if calibre is None:
            raise commands.CheckFailure("The library isn't set up on this bot.")
        if not books_available(ctx.guild):
            raise commands.CheckFailure("The library isn't available in this server.")
        return True
    return commands.check(predicate)


def book_line(book: library.Book) -> str:
    title = discord.utils.escape_markdown(book.title[:80])
    formats = ", ".join(f.name.upper() for f in book.formats)
    return f"`{book.id}` **{title}** — {discord.utils.escape_markdown(book.author_text[:60])} ({formats})"


@bot.hybrid_group(name="books", description="Search and download books from the library.", invoke_without_command=True)
@books_enabled()
async def books(ctx: commands.Context):
    await ctx.send(
        "Use `/books search <anything>` to find books, then `/books download <title or ID>` to get one.",
        ephemeral=True,
    )


@books.command(name="search", description="Search the library by title, author, series or tag.")
@books_enabled()
async def books_search(ctx: commands.Context, *, query: str):
    await ctx.defer(ephemeral=True)
    try:
        results = await calibre.search(query)
    except library.LibraryError as error:
        log.warning("Library search failed: %s", error.log_text)
        await ctx.send(str(error), ephemeral=True)
        return
    recent_books.update({book.id: book for book in results})
    if not results:
        await ctx.send(f"No books match “{discord.utils.escape_markdown(query)}”.", ephemeral=True)
        return
    pages = BookSearchPages(results, query, ctx.author.id)
    if pages.page_count == 1:
        await ctx.send(embed=pages.embed(), ephemeral=True)
        return
    pages.message = await ctx.send(embed=pages.embed(), view=pages, ephemeral=True)


class BookSearchPages(discord.ui.View):
    """Search results with ◀ / ▶ buttons to page through them."""

    def __init__(self, results: list[library.Book], query: str, author_id: int):
        super().__init__(timeout=600)
        self.results = results
        self.query = query
        self.author_id = author_id
        self.page = 0
        self.page_count = -(-len(results) // SEARCH_RESULTS_SHOWN)  # Round up.
        self.message: discord.Message | None = None
        self._update_buttons()

    def embed(self) -> discord.Embed:
        start = self.page * SEARCH_RESULTS_SHOWN
        count = len(self.results)
        embed = discord.Embed(
            title=f"📚 {count} result{'s' if count != 1 else ''} for “{self.query[:100]}”",
            description="\n".join(book_line(book) for book in self.results[start:start + SEARCH_RESULTS_SHOWN]),
            color=discord.Color.blurple(),
        )
        footer = "Get one with /books download <ID or title>."
        if self.page_count > 1:
            footer = f"Page {self.page + 1} of {self.page_count}. " + footer
        embed.set_footer(text=footer)
        return embed

    def _update_buttons(self) -> None:
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.page_count - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Matters for !books search, which posts in the channel where anyone could click.
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("These are someone else's results. Run your own `/books search`.", ephemeral=True)
            return False
        return True

    async def _show(self, interaction: discord.Interaction) -> None:
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(self.page - 1, 0)
        await self._show(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.page + 1, self.page_count - 1)
        await self._show(interaction)

    async def on_timeout(self) -> None:
        # Buttons stop working after 10 minutes, so grey them out.
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass  # Private messages can only be edited for 15 minutes; not worth failing over.


async def find_book(query: str) -> library.Book | int | list[library.Book]:
    """A book ID, a single matching book, or a list of candidates if the title is ambiguous."""
    if query.isdigit():
        return recent_books.get(int(query)) or int(query)
    results = await calibre.search(query)
    recent_books.update({book.id: book for book in results})
    exact = [book for book in results if book.title.casefold() == query.casefold()]
    if len(exact) == 1 or len(results) == 1:
        return (exact or results)[0]
    return exact or results


@books.command(name="download", description="Download a book by ID or title. Only you will see it.")
@books_enabled()
async def books_download(ctx: commands.Context, *, book: str):
    await ctx.defer(ephemeral=True)
    # Slash replies can be private; prefix commands can't, so those go by DM instead.
    size_limit = ctx.guild.filesize_limit if ctx.interaction else DM_FILE_SIZE_LIMIT
    try:
        found = await find_book(book.strip())
        if isinstance(found, list):
            if not found:
                await ctx.send(f"No books match “{discord.utils.escape_markdown(book)}”.", ephemeral=True)
            else:
                lines = "\n".join(book_line(b) for b in found[:10])
                await ctx.send(f"Several books match. Download one by its ID:\n{lines}", ephemeral=True)
            return
        if isinstance(found, int):
            download = await calibre.download_by_id(found, size_limit)
            title = download.filename.rsplit(".", 1)[0]
        else:
            download = await calibre.download(found, size_limit)
            title = found.title
    except library.LibraryError as error:
        log.warning("Library download failed: %s", error.log_text)
        await ctx.send(str(error), ephemeral=True)
        return

    # Deliberately anonymous: no user, no title.
    log.info("Library: a book was sent (%s)", library.format_size(len(download.data)))
    message = f"📖 **{discord.utils.escape_markdown(title)}**"
    file = discord.File(io.BytesIO(download.data), filename=download.filename)
    if ctx.interaction:
        await ctx.send(message, file=file, ephemeral=True)
        return
    try:
        await ctx.author.send(message, file=file)
        await ctx.reply("📬 Sent it to your DMs.")
    except discord.Forbidden:
        await ctx.reply("I couldn't DM you. Allow DMs from server members, or use `/books download` instead.")


def can_use(command: commands.Command, ctx: commands.Context) -> bool:
    """Whether to show a command in /help here."""
    if (command.root_parent or command).name == "books":
        return books_available(ctx.guild)
    return True


def command_help_embed(command: commands.Command) -> discord.Embed:
    """Detailed help for one command, e.g. /help abm."""
    embed = discord.Embed(
        title=f"/{command.name} {command.signature}".strip(),
        description=f"{command.description}\n\nAlso works as `{COMMAND_PREFIX}{command.name}`.",
        color=discord.Color.blurple(),
    )
    if isinstance(command, commands.Group):
        embed.title = f"/{command.name}"
        embed.description = f"{command.description}\n\nAlso works as `{COMMAND_PREFIX}{command.name} <subcommand>`."
        for sub in sorted(command.commands, key=lambda c: c.name):
            embed.add_field(name=f"/{sub.qualified_name} {sub.signature}".strip(), value=sub.description, inline=False)
    if command.name == "quote":
        embed.add_field(
            name="More ways to save a quote",
            value=(
                f"• **Reply** to a message with `{COMMAND_PREFIX}quote` to save it, or `{COMMAND_PREFIX}quote @someone` "
                "to credit someone else (handy when a person types out what someone said in voice).\n"
                f"• **Type it:** `{COMMAND_PREFIX}quote @someone what they said`. Add ` -- context` on the end for context.\n"
                "• **Right-click a message** → Apps → **Save quote** to edit the wording and pick who said it.\n"
                f"• `{COMMAND_PREFIX}quote` on its own gives a random quote; `{COMMAND_PREFIX}quote 12` shows quote #12."
            ),
            inline=False,
        )
    if command.name == "books":
        embed.add_field(
            name="Privacy",
            value=(f"With `/books`, search results and books are only shown to you. With `{COMMAND_PREFIX}books`, "
                   f"search results post in the channel and books are sent by DM."),
            inline=False,
        )
    if command.name in ("abm", "imperial"):
        embed.description += (
            "\n\nType a number and a metric unit, with or without a space: `3cm`, `2.5 kg`, `100 km/h`. "
            "Spelled-out names like `metres` or `litres` work too. Capitals mostly don't matter, "
            "except `mW` vs `MW`."
        )
        for dimension, units in abm.input_unit_help():
            embed.add_field(name=dimension, value=units, inline=True)
    return embed


@bot.hybrid_command(name="help", description="List everything this bot can do, or details for one command.")
async def help_command(ctx: commands.Context, command: str | None = None):
    if command:
        found = bot.get_command(command.lstrip("/" + COMMAND_PREFIX).lower())
        if found is None or not can_use(found, ctx):
            await ctx.send(f"There's no `{command}` command. Try `/help` for the list.", ephemeral=True)
        else:
            # Private for /help <command>, so the details don't fill the channel.
            await ctx.send(embed=command_help_embed(found), ephemeral=True)
        return
    embed = discord.Embed(
        title="Keep The Degenerates Inline",
        description=f"Use `/command` or `{COMMAND_PREFIX}command`.",
        color=discord.Color.blurple(),
    )
    for command in sorted(bot.commands, key=lambda c: c.name):
        if not can_use(command, ctx):
            continue  # e.g. /books outside the library servers.
        usage = (" | ".join(sorted(sub.name for sub in command.commands))
                 if isinstance(command, commands.Group) else command.signature)
        embed.add_field(
            name=f"/{command.name} {usage}".strip(),
            value=command.description or "No description.",
            inline=False,
        )
    embed.add_field(
        name=f"React {SPRAY_EMOJI}",
        value="Sprays whoever sent the message and adds to their rap sheet.",
        inline=False,
    )
    embed.set_footer(text="Use /help <command> for details, e.g. /help abm for every unit it understands.")
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
    reactor = payload.member or f"user {payload.user_id}"
    log.info("[%s] %s reacted %s, spraying user %s", channel.guild if payload.guild_id else "DM",
             reactor, SPRAY_EMOJI, payload.message_author_id)
    await channel.send(f"{target}{SPRAY_GIF_URL}")


@bot.event
async def on_ready():
    log.info("Logged in as %s (ID: %s), prefix: %r, logging to %s", bot.user, bot.user.id, COMMAND_PREFIX, LOG_FILE)


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit(f"DISCORD_TOKEN is not set. Copy .env.example to {ENV_FILE} and add your token.")
    setup_logging()
    # log_handler=None: use the logging set up above instead of discord.py's default.
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
