import io
import logging
import os
import random
import sqlite3
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

import abm
import library
import reminders

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
# Timezone that campaign reminder times are in, e.g. "mondays at 1800" means 18:00 here (summer time handled).
try:
    REMINDER_TIMEZONE = ZoneInfo(os.getenv("REMINDER_TIMEZONE") or "Europe/London")
except (ZoneInfoNotFoundError, ValueError):
    logging.getLogger("ktdi").warning("Unknown REMINDER_TIMEZONE %r, using UTC.", os.getenv("REMINDER_TIMEZONE"))
    REMINDER_TIMEZONE = ZoneInfo("UTC")
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

# The /linux target (@poltergeis.t). Override with LINUX_HATER_ID in .env.
LINUX_HATER_ID = os.getenv("LINUX_HATER_ID") or "351350774435151873"

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
db.execute(
    """
    CREATE TABLE IF NOT EXISTS campaigns (
        guild_id      INTEGER NOT NULL,
        alias         TEXT NOT NULL,  -- as typed, e.g. "Monday game"
        alias_key     TEXT NOT NULL,  -- lowercased, for case-insensitive lookups
        dndbeyond_url TEXT,
        vtt_url       TEXT,
        added_by      INTEGER NOT NULL,
        created_at    TEXT NOT NULL,
        PRIMARY KEY (guild_id, alias_key)
    )
    """
)
db.execute(
    """
    CREATE TABLE IF NOT EXISTS campaign_reminders (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id    INTEGER NOT NULL,
        alias_key   TEXT NOT NULL,     -- the campaign it belongs to (one reminder per campaign)
        channel_id  INTEGER NOT NULL,  -- where the reminders are posted
        message_id  INTEGER,           -- the setup message people react 🔔 to
        days        TEXT NOT NULL,     -- "0,3" = Mondays and Thursdays
        time        TEXT NOT NULL,     -- "18:00", in REMINDER_TIMEZONE
        every_weeks INTEGER NOT NULL,  -- 1 weekly, 2 fortnightly
        anchor      TEXT NOT NULL,     -- a date in an "on" week, for fortnightly schedules
        next_run    TEXT NOT NULL,     -- ISO 8601, UTC
        created_by  INTEGER NOT NULL,
        UNIQUE (guild_id, alias_key)
    )
    """
)
db.execute(
    """
    CREATE TABLE IF NOT EXISTS campaign_reminder_subscribers (
        reminder_id INTEGER NOT NULL,
        user_id     INTEGER NOT NULL,
        PRIMARY KEY (reminder_id, user_id)
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


ANONYMOUS = 0  # user_id for quotes that aren't credited to anyone.
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


def anonymise_quote(guild_id: int, quote_id: int) -> None:
    # The message link goes too, since it would show who wrote it.
    db.execute("UPDATE quotes SET user_id = ?, channel_id = NULL, message_id = NULL WHERE guild_id = ? AND id = ?",
               (ANONYMOUS, guild_id, quote_id))
    db.commit()


def claim_quote(guild_id: int, quote_id: int, user_id: int) -> None:
    db.execute("UPDATE quotes SET user_id = ? WHERE guild_id = ? AND id = ? AND user_id = ?",
               (user_id, guild_id, quote_id, ANONYMOUS))
    db.commit()


def delete_quote(guild_id: int, quote_id: int) -> None:
    db.execute("DELETE FROM quotes WHERE guild_id = ? AND id = ?", (guild_id, quote_id))
    db.commit()


@dataclass
class Campaign:
    guild_id: int
    alias: str
    dndbeyond_url: str | None
    vtt_url: str | None
    added_by: int


CAMPAIGN_COLUMNS = "guild_id, alias, dndbeyond_url, vtt_url, added_by"


def get_campaign(guild_id: int, alias: str) -> Campaign | None:
    row = db.execute(f"SELECT {CAMPAIGN_COLUMNS} FROM campaigns WHERE guild_id = ? AND alias_key = ?",
                     (guild_id, alias.strip().casefold())).fetchone()
    return Campaign(*row) if row else None


def list_campaigns(guild_id: int) -> list[Campaign]:
    rows = db.execute(f"SELECT {CAMPAIGN_COLUMNS} FROM campaigns WHERE guild_id = ? ORDER BY alias_key",
                      (guild_id,)).fetchall()
    return [Campaign(*row) for row in rows]


def save_campaign(guild_id: int, alias: str, dndbeyond_url: str | None, vtt_url: str | None, added_by: int) -> None:
    db.execute(
        "INSERT INTO campaigns (guild_id, alias, alias_key, dndbeyond_url, vtt_url, added_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (guild_id, alias, alias.casefold(), dndbeyond_url, vtt_url, added_by,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    db.commit()


def update_campaign(guild_id: int, old_alias: str, alias: str, dndbeyond_url: str | None, vtt_url: str | None) -> None:
    db.execute(
        "UPDATE campaigns SET alias = ?, alias_key = ?, dndbeyond_url = ?, vtt_url = ? WHERE guild_id = ? AND alias_key = ?",
        (alias, alias.casefold(), dndbeyond_url, vtt_url, guild_id, old_alias.casefold()),
    )
    # Keep the reminder attached through a rename.
    db.execute("UPDATE campaign_reminders SET alias_key = ? WHERE guild_id = ? AND alias_key = ?",
               (alias.casefold(), guild_id, old_alias.casefold()))
    db.commit()


def delete_campaign(guild_id: int, alias: str) -> None:
    delete_reminder(guild_id, alias)
    db.execute("DELETE FROM campaigns WHERE guild_id = ? AND alias_key = ?", (guild_id, alias.casefold()))
    db.commit()


@dataclass
class Reminder:
    id: int
    guild_id: int
    alias_key: str
    channel_id: int
    message_id: int | None
    days: str
    time: str
    every_weeks: int
    anchor: str
    next_run: str
    created_by: int

    @property
    def schedule(self) -> reminders.Schedule:
        return reminders.Schedule.from_storage(self.days, self.time, self.every_weeks)

    @property
    def next_run_at(self) -> datetime:
        return datetime.fromisoformat(self.next_run)


REMINDER_COLUMNS = "id, guild_id, alias_key, channel_id, message_id, days, time, every_weeks, anchor, next_run, created_by"


def get_reminder(guild_id: int, alias: str) -> Reminder | None:
    row = db.execute(f"SELECT {REMINDER_COLUMNS} FROM campaign_reminders WHERE guild_id = ? AND alias_key = ?",
                     (guild_id, alias.casefold())).fetchone()
    return Reminder(*row) if row else None


def reminder_for_message(message_id: int) -> Reminder | None:
    row = db.execute(f"SELECT {REMINDER_COLUMNS} FROM campaign_reminders WHERE message_id = ?", (message_id,)).fetchone()
    return Reminder(*row) if row else None


def due_reminders(now: datetime) -> list[Reminder]:
    rows = db.execute(f"SELECT {REMINDER_COLUMNS} FROM campaign_reminders WHERE next_run <= ?",
                      (now.isoformat(timespec="seconds"),)).fetchall()
    return [Reminder(*row) for row in rows]


def save_reminder(guild_id: int, alias: str, channel_id: int, schedule: reminders.Schedule, anchor: date,
                  next_run: datetime, created_by: int) -> int:
    """Create the campaign's reminder, replacing any existing one (and its subscribers)."""
    delete_reminder(guild_id, alias)
    days, clock, every_weeks = schedule.to_storage()
    cursor = db.execute(
        "INSERT INTO campaign_reminders (guild_id, alias_key, channel_id, days, time, every_weeks, anchor, next_run, created_by)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (guild_id, alias.casefold(), channel_id, days, clock, every_weeks, anchor.isoformat(),
         next_run.isoformat(timespec="seconds"), created_by),
    )
    db.commit()
    return cursor.lastrowid


def set_reminder_message(reminder_id: int, message_id: int) -> None:
    db.execute("UPDATE campaign_reminders SET message_id = ? WHERE id = ?", (message_id, reminder_id))
    db.commit()


def update_reminder_schedule(reminder_id: int, schedule: reminders.Schedule, anchor: date, next_run: datetime) -> None:
    """Change when a reminder goes off, keeping its setup message and subscribers."""
    days, clock, every_weeks = schedule.to_storage()
    db.execute("UPDATE campaign_reminders SET days = ?, time = ?, every_weeks = ?, anchor = ?, next_run = ? WHERE id = ?",
               (days, clock, every_weeks, anchor.isoformat(), next_run.isoformat(timespec="seconds"), reminder_id))
    db.commit()


def set_next_run(reminder_id: int, next_run: datetime) -> None:
    db.execute("UPDATE campaign_reminders SET next_run = ? WHERE id = ?",
               (next_run.isoformat(timespec="seconds"), reminder_id))
    db.commit()


def delete_reminder(guild_id: int, alias: str) -> None:
    existing = get_reminder(guild_id, alias)
    if existing:
        db.execute("DELETE FROM campaign_reminder_subscribers WHERE reminder_id = ?", (existing.id,))
        db.execute("DELETE FROM campaign_reminders WHERE id = ?", (existing.id,))
        db.commit()


def subscribe(reminder_id: int, user_id: int) -> None:
    db.execute("INSERT OR IGNORE INTO campaign_reminder_subscribers (reminder_id, user_id) VALUES (?, ?)",
               (reminder_id, user_id))
    db.commit()


def unsubscribe(reminder_id: int, user_id: int) -> None:
    db.execute("DELETE FROM campaign_reminder_subscribers WHERE reminder_id = ? AND user_id = ?", (reminder_id, user_id))
    db.commit()


def subscribers(reminder_id: int) -> list[int]:
    rows = db.execute("SELECT user_id FROM campaign_reminder_subscribers WHERE reminder_id = ? ORDER BY rowid",
                      (reminder_id,)).fetchall()
    return [row[0] for row in rows]


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
        reminder_loop.start()
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


def said_by(quote: Quote) -> str:
    return "*Anonymous*" if quote.user_id == ANONYMOUS else f"<@{quote.user_id}>"


def quote_embed(quote: Quote) -> discord.Embed:
    description = f"“{quote.text}”\n— {said_by(quote)}"
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


def save_quote(guild: discord.Guild, channel_id: int | None, added_by: discord.abc.User, speaker_id: int,
               text: str | None, context: str | None, source: discord.Message | None = None) -> Reply:
    """Save a quote. speaker_id=ANONYMOUS saves it uncredited (and without a link to the original message)."""
    text = (text or "").strip()
    context = (context or "").strip() or None
    if not text:
        if source:
            return Reply("That message has no text, so type the quote in with `/quote add`.", private=True)
        return Reply("There's nothing to quote. Add what was said.", private=True)
    if len(text) > QUOTE_MAX_LENGTH:
        return Reply(f"That's a bit long for a quote (max {QUOTE_MAX_LENGTH} characters).", private=True)
    if context and len(context) > QUOTE_CONTEXT_MAX_LENGTH:
        return Reply(f"The context is too long (max {QUOTE_CONTEXT_MAX_LENGTH} characters).", private=True)
    anonymous = speaker_id == ANONYMOUS
    if anonymous:
        channel_id = source = None  # A link to the original message would give away who said it.
    if source:
        existing = quote_for_message(guild.id, source.id)
        if existing and existing.text == text and existing.user_id == speaker_id:
            return Reply(f"That's already saved as quote #{existing.id}.", private=True)
    quote_id = add_quote(guild.id, speaker_id, text, context, added_by.id, channel_id, source.id if source else None)
    log.info("[%s] %s saved %squote #%d", guild.name, added_by, "an anonymous " if anonymous else "", quote_id)
    label = "anonymous quote" if anonymous else "quote"
    return Reply(f"📌 Saved {label} #{quote_id}.", quote_embed(get_quote(guild.id, quote_id)))


def dissociate_quote(guild: discord.Guild, member: discord.Member, number: int) -> Reply:
    quote = get_quote(guild.id, number)
    if quote is None:
        return Reply(f"There's no quote #{number}.", private=True)
    if quote.user_id == ANONYMOUS:
        return Reply(f"Quote #{number} is already anonymous.", private=True)
    if member.id not in (quote.added_by, quote.user_id) and not member.guild_permissions.manage_messages:
        return Reply(f"Only the person quoted, whoever saved it, or a moderator can make quote #{number} anonymous.",
                     private=True)
    anonymise_quote(guild.id, number)
    # Deliberately doesn't log who asked: that alone would reveal whose quote it was.
    log.info("[%s] Quote #%d was made anonymous", guild.name, number)
    return Reply(f"🕶️ Quote #{number} is now anonymous.", quote_embed(get_quote(guild.id, number)))


def claim(guild: discord.Guild, member: discord.Member, number: int) -> Reply:
    """Put your own name on an anonymous quote. Only ever yourself, so nobody can undo someone's dissociate."""
    quote = get_quote(guild.id, number)
    if quote is None:
        return Reply(f"There's no quote #{number}.", private=True)
    if quote.user_id == member.id:
        return Reply(f"Quote #{number} is already yours.", private=True)
    if quote.user_id != ANONYMOUS:
        return Reply(f"Quote #{number} isn't anonymous, so it can't be claimed.", private=True)
    claim_quote(guild.id, number, member.id)
    log.info("[%s] %s claimed quote #%d", guild.name, member, number)
    return Reply(f"🙋 {member.mention} claimed quote #{number}.", quote_embed(get_quote(guild.id, number)))


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
    return f"`#{quote.id}` “{text}” — {said_by(quote)} · <t:{when}:d>"


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
    speaker = int(match.group(1)) if match else None
    text = (match.group(2) if match else args).strip()
    try:
        replied = await replied_message(ctx)
    except discord.HTTPException:
        await ctx.send("I couldn't read the message you replied to. I need the Read Message History permission here.")
        return

    if replied:
        # "!quote" or "!quote @Dave" as a reply saves that message; any text typed replaces its wording.
        quote_text, context = split_context(text)
        reply = save_quote(ctx.guild, ctx.channel.id, ctx.author, speaker or replied.author.id,
                           quote_text or replied.content, context, replied)
    elif speaker is None and text.isdigit():
        reply = show_quote(ctx.guild, int(text))
    elif text and speaker is None:
        reply = Reply(f"Who said it? Use `{COMMAND_PREFIX}quote @someone what they said`, reply to their message "
                      f"with `{COMMAND_PREFIX}quote`, or use `{COMMAND_PREFIX}quote anon what was said`.")
    elif text:
        quote_text, context = split_context(text)
        reply = save_quote(ctx.guild, ctx.channel.id, ctx.author, speaker, quote_text, context)
    else:
        # "!quote" or "!quote @Dave" on its own: a random quote.
        user = discord.utils.get(ctx.message.mentions, id=speaker) if speaker else None
        reply = show_random_quote(ctx.guild, user)
    await send_reply(ctx, reply)


# Prefix only: in /quote add you just leave the user empty. Marked so /help shows it as !quote anon.
@quote_prefix.command(name="anon", aliases=["anonymous"], description="Save a quote without crediting anyone.",
                      extras={"prefix_only": True})
async def quote_prefix_anon(ctx: commands.Context, *, text: str = ""):
    try:
        replied = await replied_message(ctx)
    except discord.HTTPException:
        replied = None
    quote_text, context = split_context(text)
    if not quote_text and replied is None:
        await send_reply(ctx, Reply(f"What was said? `{COMMAND_PREFIX}quote anon what was said`, "
                                    f"or reply to a message with `{COMMAND_PREFIX}quote anon`."))
        return
    await send_reply(ctx, save_quote(ctx.guild, ctx.channel.id, ctx.author, ANONYMOUS,
                                     quote_text or replied.content, context))


@quote_prefix.command(name="claim", aliases=["update"], description="Put your own name on an anonymous quote.")
async def quote_prefix_claim(ctx: commands.Context, number: int):
    await send_reply(ctx, claim(ctx.guild, ctx.author, number))


@quote_prefix.command(name="dissociate", aliases=["anonymise", "anonymize"],
                      description="Remove the name from a quote, keeping the quote (the person quoted, whoever saved it, or a mod).")
async def quote_prefix_dissociate(ctx: commands.Context, number: int):
    await send_reply(ctx, dissociate_quote(ctx.guild, ctx.author, number))


@quote_prefix.command(name="add", usage="<text> [user] [context]",  # Shown in /help, which describes the slash version.
                      description="Save something someone said. Leave out the user for an anonymous quote.")
async def quote_prefix_add(ctx: commands.Context, user: discord.Member | None = None, *, text: str = ""):
    # "!quote add @Dave text", "!quote add anon text" and "!quote add text" (anonymous) all work.
    if user is None:
        first, _, rest = text.partition(" ")
        if first.lower() in ("anon", "anonymous"):
            text = rest
    quote_text, context = split_context(text)
    await send_reply(ctx, save_quote(ctx.guild, ctx.channel.id, ctx.author, user.id if user else ANONYMOUS,
                                     quote_text, context))


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
@app_commands.describe(text="What they said", user="Who said it. Leave empty to save it anonymously",
                       context="Optional: what was going on at the time")
async def quote_slash_add(interaction: discord.Interaction, text: app_commands.Range[str, 1, QUOTE_MAX_LENGTH],
                          user: discord.Member | None = None,
                          context: app_commands.Range[str, 1, QUOTE_CONTEXT_MAX_LENGTH] | None = None):
    speaker = user.id if user else ANONYMOUS
    await respond(interaction, save_quote(interaction.guild, interaction.channel_id, interaction.user, speaker, text, context))


@quote_slash.command(name="dissociate",
                     description="Remove the name from a quote, keeping the quote (the person quoted, whoever saved it, or a mod).")
async def quote_slash_dissociate(interaction: discord.Interaction, number: int):
    await respond(interaction, dissociate_quote(interaction.guild, interaction.user, number))


@quote_slash.command(name="claim", description="Put your own name on an anonymous quote.")
@app_commands.describe(number="The anonymous quote's number")
async def quote_slash_claim(interaction: discord.Interaction, number: int):
    await respond(interaction, claim(interaction.guild, interaction.user, number))


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
        self.said_by = discord.ui.UserSelect(default_values=[discord.Object(id=source.author.id)],
                                             required=False, min_values=0)
        self.context = discord.ui.TextInput(required=False, max_length=QUOTE_CONTEXT_MAX_LENGTH,
                                            placeholder="e.g. mid-fight, right after rolling a nat 1")
        self.add_item(discord.ui.Label(text="Quote", component=self.quote_text))
        self.add_item(discord.ui.Label(text="Who said it?", component=self.said_by,
                                       description="Change it if someone typed out what another person said, "
                                                   "or clear it to save anonymously."))
        self.add_item(discord.ui.Label(text="Context (optional)", component=self.context))

    async def on_submit(self, interaction: discord.Interaction):
        speaker = self.said_by.values[0].id if self.said_by.values else ANONYMOUS  # Cleared picker = anonymous.
        await respond(interaction, save_quote(interaction.guild, self.source.channel.id, interaction.user, speaker,
                                              self.quote_text.value, self.context.value, self.source))


@bot.tree.context_menu(name="Save quote")
@app_commands.guild_only()
async def save_quote_menu(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.send_modal(SaveQuoteModal(message))


# --- Campaigns: an alias ("Monday game") pointing at a D&D Beyond campaign and a VTT ---
CAMPAIGN_ALIAS_MAX = 50
# Can't be aliases, or !campaign <alias> would clash.
CAMPAIGN_SUBCOMMANDS = {"add", "edit", "list", "remove", "show", "remind", "unremind", "reschedule", "skip"}
REMINDER_EMOJI = "🔔"
REMINDER_GRACE = timedelta(hours=1)  # If the bot was down at reminder time, still send it up to this late.
CLEAR_LINK = "none"  # Pass this to /campaign edit to remove a link.
KNOWN_VTTS = {
    "roll20.net": "Roll20",
    "owlbear.rodeo": "Owlbear Rodeo",
    "forge-vtt.com": "The Forge",
    "foundryvtt.com": "Foundry",
    "fantasygrounds.com": "Fantasy Grounds",
    "alchemyrpg.com": "Alchemy",
    "talespire.com": "TaleSpire",
    "dndbeyond.com": "D&D Beyond Maps",
}


class CampaignError(Exception):
    """A problem with what the user typed. The message is safe to show them."""


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def on_domain(url: str, domain: str) -> bool:
    host = host_of(url)
    return host == domain or host.endswith("." + domain)


def vtt_label(url: str) -> str:
    """Name the VTT button after the site where we recognise it, e.g. Roll20. Self-hosted Foundry etc. is just 'VTT'."""
    return next((label for domain, label in KNOWN_VTTS.items() if on_domain(url, domain)), "VTT")


def clean_link(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    link = value.strip().strip("<>")  # People often wrap links in <> to stop Discord previewing them.
    parsed = urlparse(link)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise CampaignError(f"`{value[:100]}` doesn't look like a link. Paste the full address, starting with https://.")
    return link


def sort_links(first: str | None, second: str | None) -> tuple[str | None, str | None]:
    """Work out which link is D&D Beyond and which is the VTT, whichever order they were given in."""
    links = [link for link in (clean_link(first), clean_link(second)) if link]
    dndbeyond = [link for link in links if on_domain(link, "dndbeyond.com") and "/campaigns/" in link]
    others = [link for link in links if link not in dndbeyond]
    if len(dndbeyond) > 1 or len(others) > 1:
        raise CampaignError("Give one D&D Beyond campaign link and one VTT link.")
    return (dndbeyond[0] if dndbeyond else None), (others[0] if others else None)


def campaign_embed(campaign: Campaign) -> discord.Embed:
    lines = []
    if campaign.dndbeyond_url:
        lines.append(f"**D&D Beyond:** {campaign.dndbeyond_url}")
    if campaign.vtt_url:
        lines.append(f"**{vtt_label(campaign.vtt_url)}:** {campaign.vtt_url}")
    reminder = get_reminder(campaign.guild_id, campaign.alias)
    if reminder:
        lines.append(f"**Reminder:** {reminder_summary(reminder)}")
    return discord.Embed(title=f"🎲 {campaign.alias}", description="\n".join(lines), color=discord.Color.dark_red())


def reminder_summary(reminder: Reminder) -> str:
    """e.g. 'Mondays at 18:00 · next <in 3 days> · 4 subscribed'."""
    count = len(subscribers(reminder.id))
    next_at = int(reminder.next_run_at.timestamp())
    return f"⏰ {reminder.schedule.describe()} · next <t:{next_at}:R> · {count} subscribed"


def campaign_buttons(campaign: Campaign) -> discord.ui.View:
    view = discord.ui.View(timeout=None)  # Link buttons open the URL directly, so there's nothing to time out.
    if campaign.dndbeyond_url:
        view.add_item(discord.ui.Button(label="D&D Beyond", url=campaign.dndbeyond_url))
    if campaign.vtt_url:
        view.add_item(discord.ui.Button(label=vtt_label(campaign.vtt_url), url=campaign.vtt_url))
    return view


def can_manage_campaign(member: discord.Member, campaign: Campaign) -> bool:
    return member.id == campaign.added_by or member.guild_permissions.manage_messages


def check_alias(alias: str) -> str:
    alias = " ".join(alias.split())  # Tidy stray spaces.
    if not alias:
        raise CampaignError("Give the campaign an alias, like `Monday game`.")
    if len(alias) > CAMPAIGN_ALIAS_MAX:
        raise CampaignError(f"That alias is too long (max {CAMPAIGN_ALIAS_MAX} characters).")
    if alias.casefold() in CAMPAIGN_SUBCOMMANDS:
        raise CampaignError(f"`{alias}` is a command name, so it can't be an alias. Try something like `{alias} game`.")
    if "://" in alias:
        raise CampaignError("The alias goes first, then the links. With `!campaign add`, put a multi-word alias in "
                            "quotes: `!campaign add \"Monday game\" <link> <link>`.")
    return alias


async def send_campaign_reply(ctx: commands.Context, content: str | None = None, campaign: Campaign | None = None,
                              embed: discord.Embed | None = None, private: bool = False) -> None:
    kwargs = {"allowed_mentions": NO_PINGS, "ephemeral": private}
    if campaign:
        kwargs["embed"], kwargs["view"] = campaign_embed(campaign), campaign_buttons(campaign)
    elif embed:
        kwargs["embed"] = embed
    await ctx.send(content, **kwargs)


@bot.hybrid_group(name="campaign", description="Our campaigns' D&D Beyond and VTT links, by alias.",
                  invoke_without_command=True)
@commands.guild_only()
async def campaign_group(ctx: commands.Context, *, alias: str = ""):
    # Prefix only: "!campaign Monday game" shows it, "!campaign" lists them all.
    if alias:
        await campaign_show.callback(ctx, alias=alias)
    else:
        await campaign_list.callback(ctx)


@campaign_group.command(name="show", description="Show a campaign's links.")
@app_commands.describe(alias="The campaign's alias, e.g. Monday game")
async def campaign_show(ctx: commands.Context, *, alias: str):
    campaign = get_campaign(ctx.guild.id, alias)
    if campaign is None:
        await send_campaign_reply(ctx, f"There's no campaign called “{discord.utils.escape_markdown(alias)}”. "
                                       "See them all with `/campaign list`.", private=True)
        return
    await send_campaign_reply(ctx, campaign=campaign)


@campaign_group.command(name="list", description="List all our campaigns.")
async def campaign_list(ctx: commands.Context):
    campaigns = list_campaigns(ctx.guild.id)
    if not campaigns:
        await send_campaign_reply(ctx, "No campaigns yet. Add one with `/campaign add`.", private=True)
        return
    lines = []
    for c in campaigns:
        links = [f"[D&D Beyond]({c.dndbeyond_url})"] if c.dndbeyond_url else []
        if c.vtt_url:
            links.append(f"[{vtt_label(c.vtt_url)}]({c.vtt_url})")
        lines.append(f"**{discord.utils.escape_markdown(c.alias)}** · " + " · ".join(links))
        reminder = get_reminder(c.guild_id, c.alias)
        if reminder:
            lines.append(f"  ⏰ {reminder.schedule.describe()} · next <t:{int(reminder.next_run_at.timestamp())}:R>")
    embed = discord.Embed(title="🎲 Campaigns", description="\n".join(lines), color=discord.Color.dark_red())
    embed.set_footer(text="Show one with its buttons: /campaign show <alias>")
    await send_campaign_reply(ctx, embed=embed)


@campaign_group.command(name="add", description="Add a campaign: an alias plus its D&D Beyond and/or VTT link.")
@app_commands.describe(alias="Anything that means something to you, e.g. Monday game",
                       dndbeyond="The D&D Beyond campaign link", vtt="The VTT link (Roll20, Foundry, Owlbear…)")
async def campaign_add(ctx: commands.Context, alias: str, dndbeyond: str | None = None, vtt: str | None = None):
    try:
        alias = check_alias(alias)
        dndbeyond, vtt = sort_links(dndbeyond, vtt)
    except CampaignError as error:
        await send_campaign_reply(ctx, str(error), private=True)
        return
    if not dndbeyond and not vtt:
        await send_campaign_reply(ctx, "Add at least one link: the D&D Beyond campaign, the VTT, or both.", private=True)
        return
    if get_campaign(ctx.guild.id, alias):
        await send_campaign_reply(ctx, f"There's already a campaign called “{alias}”. Change it with `/campaign edit`.",
                                  private=True)
        return
    save_campaign(ctx.guild.id, alias, dndbeyond, vtt, ctx.author.id)
    log.info("[%s] %s added campaign %r", ctx.guild.name, ctx.author, alias)
    await send_campaign_reply(ctx, "🎲 Campaign added.", campaign=get_campaign(ctx.guild.id, alias))


@campaign_group.command(name="edit", description="Change a campaign's links or alias (whoever added it, or a mod).")
@app_commands.describe(alias="The campaign to change", dndbeyond=f"New D&D Beyond link, or '{CLEAR_LINK}' to remove it",
                       vtt=f"New VTT link, or '{CLEAR_LINK}' to remove it", rename="A new alias")
async def campaign_edit(ctx: commands.Context, alias: str, dndbeyond: str | None = None, vtt: str | None = None,
                        rename: str | None = None):
    campaign = get_campaign(ctx.guild.id, alias)
    if campaign is None:
        await send_campaign_reply(ctx, f"There's no campaign called “{discord.utils.escape_markdown(alias)}”.", private=True)
        return
    if not can_manage_campaign(ctx.author, campaign):
        await send_campaign_reply(ctx, "Only whoever added this campaign, or a moderator, can change it.", private=True)
        return
    try:
        new_alias = check_alias(rename) if rename else campaign.alias
        new_dndbeyond = None if (dndbeyond or "").strip().lower() == CLEAR_LINK else (clean_link(dndbeyond) or campaign.dndbeyond_url)
        new_vtt = None if (vtt or "").strip().lower() == CLEAR_LINK else (clean_link(vtt) or campaign.vtt_url)
        if new_dndbeyond and not on_domain(new_dndbeyond, "dndbeyond.com"):
            raise CampaignError("That isn't a D&D Beyond link. Put other links in `vtt`.")
    except CampaignError as error:
        await send_campaign_reply(ctx, str(error), private=True)
        return
    if not new_dndbeyond and not new_vtt:
        await send_campaign_reply(ctx, "A campaign needs at least one link. Use `/campaign remove` to delete it.", private=True)
        return
    if new_alias.casefold() != campaign.alias.casefold() and get_campaign(ctx.guild.id, new_alias):
        await send_campaign_reply(ctx, f"There's already a campaign called “{new_alias}”.", private=True)
        return
    update_campaign(ctx.guild.id, campaign.alias, new_alias, new_dndbeyond, new_vtt)
    log.info("[%s] %s edited campaign %r", ctx.guild.name, ctx.author, new_alias)
    await send_campaign_reply(ctx, "✏️ Campaign updated.", campaign=get_campaign(ctx.guild.id, new_alias))


@campaign_group.command(name="remove", description="Remove a campaign (whoever added it, or a mod).")
@app_commands.describe(alias="The campaign to remove")
async def campaign_remove(ctx: commands.Context, *, alias: str):
    campaign = get_campaign(ctx.guild.id, alias)
    if campaign is None:
        await send_campaign_reply(ctx, f"There's no campaign called “{discord.utils.escape_markdown(alias)}”.", private=True)
        return
    if not can_manage_campaign(ctx.author, campaign):
        await send_campaign_reply(ctx, "Only whoever added this campaign, or a moderator, can remove it.", private=True)
        return
    delete_campaign(ctx.guild.id, campaign.alias)
    log.info("[%s] %s removed campaign %r", ctx.guild.name, ctx.author, campaign.alias)
    await send_campaign_reply(ctx, f"🗑️ Removed the campaign “{campaign.alias}”.")


def can_manage_reminder(member: discord.Member, reminder: Reminder, campaign: Campaign) -> bool:
    return member.id in (reminder.created_by, campaign.added_by) or member.guild_permissions.manage_messages


def plan_schedule(text: str, now: datetime, keep_anchor: date | None = None) -> tuple[reminders.Schedule, datetime, date]:
    """Parse 'every other monday at 7pm [from 19 oct]' into (schedule, first reminder, anchor)."""
    schedule_text, start_text = reminders.split_start(text)
    schedule = reminders.parse_schedule(schedule_text)
    if start_text:
        start = reminders.parse_date(start_text, now.astimezone(REMINDER_TIMEZONE).date())
        first, anchor = reminders.first_on_or_after(schedule, start, now, REMINDER_TIMEZONE)
    else:
        first = reminders.next_occurrence(schedule, now, REMINDER_TIMEZONE, keep_anchor)
        anchor = keep_anchor or first.astimezone(REMINDER_TIMEZONE).date()
    return schedule, first, anchor


def when_text(moment: datetime) -> str:
    return f"<t:{int(moment.timestamp())}:F> (<t:{int(moment.timestamp())}:R>)"


@campaign_group.command(name="remind", description="Remind the group on a schedule, e.g. mondays at 1800. React 🔔 to get pinged.")
@app_commands.describe(alias="The campaign",
                       when="e.g. mondays at 1800, monday 6pm, every other friday at 7:30pm from 23 oct")
async def campaign_remind(ctx: commands.Context, alias: str, *, when: str):
    campaign = get_campaign(ctx.guild.id, alias)
    if campaign is None:
        await send_campaign_reply(ctx, f"There's no campaign called “{discord.utils.escape_markdown(alias)}”. "
                                       "Add it first with `/campaign add`.", private=True)
        return
    existing = get_reminder(ctx.guild.id, campaign.alias)
    if existing and not can_manage_reminder(ctx.author, existing, campaign):
        await send_campaign_reply(ctx, "This campaign already has a reminder. Only whoever set it, whoever added the "
                                       "campaign, or a moderator can replace it.", private=True)
        return
    now = datetime.now(timezone.utc)
    try:
        schedule, first, anchor = plan_schedule(when, now)
    except reminders.ScheduleError as error:
        await send_campaign_reply(ctx, str(error), private=True)
        return
    reminder_id = save_reminder(ctx.guild.id, campaign.alias, ctx.channel.id, schedule, anchor, first, ctx.author.id)
    log.info("[%s] %s set a reminder for %r: %s", ctx.guild.name, ctx.author, campaign.alias, schedule.describe())

    embed = discord.Embed(
        title=f"⏰ Reminder: {campaign.alias}",
        description=(f"**{schedule.describe()}** ({REMINDER_TIMEZONE.key} time)\n"
                     f"First one: {when_text(first)}\n\n"
                     f"**React {REMINDER_EMOJI} to this message to get pinged.** Remove your {REMINDER_EMOJI} to stop."),
        color=discord.Color.dark_red(),
    )
    replaced = " It replaces the old one, so react again if you want pings." if existing else ""
    message = await ctx.send(f"⏰ Reminder set.{replaced}", embed=embed, allowed_mentions=NO_PINGS)
    set_reminder_message(reminder_id, message.id)
    try:
        await message.add_reaction(REMINDER_EMOJI)  # So people can just click it.
    except discord.HTTPException:
        pass  # Missing Add Reactions / Read Message History: people can still add 🔔 themselves.


@campaign_group.command(name="unremind", description="Stop a campaign's reminders.")
@app_commands.describe(alias="The campaign")
async def campaign_unremind(ctx: commands.Context, *, alias: str):
    campaign = get_campaign(ctx.guild.id, alias)
    reminder = get_reminder(ctx.guild.id, alias)
    if campaign is None or reminder is None:
        await send_campaign_reply(ctx, f"“{discord.utils.escape_markdown(alias)}” doesn't have a reminder.", private=True)
        return
    if not can_manage_reminder(ctx.author, reminder, campaign):
        await send_campaign_reply(ctx, "Only whoever set the reminder, whoever added the campaign, or a moderator can "
                                       "stop it. To stop your own pings, remove your 🔔 from the reminder message.",
                                  private=True)
        return
    delete_reminder(ctx.guild.id, campaign.alias)
    log.info("[%s] %s stopped the reminder for %r", ctx.guild.name, ctx.author, campaign.alias)
    await send_campaign_reply(ctx, f"🔕 Stopped the reminders for “{campaign.alias}”.")


async def reminder_to_change(ctx: commands.Context, alias: str) -> tuple[Campaign, Reminder] | None:
    """Look up a campaign's reminder and check the user may change it, replying if not."""
    campaign = get_campaign(ctx.guild.id, alias)
    reminder = get_reminder(ctx.guild.id, alias) if campaign else None
    if campaign is None or reminder is None:
        await send_campaign_reply(ctx, f"“{discord.utils.escape_markdown(alias)}” doesn't have a reminder. "
                                       "Set one with `/campaign remind`.", private=True)
        return None
    if not can_manage_reminder(ctx.author, reminder, campaign):
        await send_campaign_reply(ctx, "Only whoever set the reminder, whoever added the campaign, or a moderator can "
                                       "change it.", private=True)
        return None
    return campaign, reminder


@campaign_group.command(name="reschedule",
                        description="Change a reminder's schedule or next date, keeping everyone's 🔔.")
@app_commands.describe(alias="The campaign",
                       change="e.g. next 26 oct · every other monday 7pm · mondays 6pm from 12 oct")
async def campaign_reschedule(ctx: commands.Context, alias: str, *, change: str):
    found = await reminder_to_change(ctx, alias)
    if found is None:
        return
    campaign, reminder = found
    now = datetime.now(timezone.utc)
    try:
        if change.strip().lower().startswith("next "):
            # "next 26 oct": same schedule, but the next session (and a fortnightly cadence) moves to that date.
            schedule = reminder.schedule
            session = reminders.parse_date(change.strip()[5:], now.astimezone(REMINDER_TIMEZONE).date())
            if session.weekday() not in schedule.days:
                raise reminders.ScheduleError(f"{session:%A %d %b} isn't on the schedule ({schedule.describe()}). "
                                              "To change the day too, give the full schedule, e.g. "
                                              f"`{'every other ' if schedule.every_weeks > 1 else ''}{session:%A} "
                                              f"at {reminder.time} from {session:%d %b}`.")
            first, anchor = reminders.first_on_or_after(schedule, session, now, REMINDER_TIMEZONE)
            if first.astimezone(REMINDER_TIMEZONE).date() != session:
                raise reminders.ScheduleError(f"The {reminder.time} reminder on {session:%d %b} has already passed.")
        else:
            schedule, first, anchor = plan_schedule(change, now, keep_anchor=date.fromisoformat(reminder.anchor))
    except reminders.ScheduleError as error:
        await send_campaign_reply(ctx, str(error), private=True)
        return
    update_reminder_schedule(reminder.id, schedule, anchor, first)
    log.info("[%s] %s rescheduled the reminder for %r: %s", ctx.guild.name, ctx.author, campaign.alias,
             schedule.describe())
    await send_campaign_reply(ctx, f"🗓️ Reminder for **{campaign.alias}** updated: {schedule.describe()}.\n"
                                   f"Next one: {when_text(first)}. Everyone's {REMINDER_EMOJI} still counts.")


@campaign_group.command(name="skip", description="Skip the next reminder. Fortnightly games shift a week and carry on from there.")
@app_commands.describe(alias="The campaign")
async def campaign_skip(ctx: commands.Context, *, alias: str):
    found = await reminder_to_change(ctx, alias)
    if found is None:
        return
    campaign, reminder = found
    schedule = reminder.schedule
    upcoming = reminder.next_run_at.astimezone(REMINDER_TIMEZONE)
    if schedule.every_weeks > 1:
        # Push the whole fortnightly cadence back a week, so it stays in step after the skipped week.
        moved = datetime.combine(upcoming.date() + timedelta(days=7), upcoming.time(), tzinfo=REMINDER_TIMEZONE)
        next_run, anchor = moved.astimezone(timezone.utc), moved.date()
        note = "The fortnightly schedule carries on from there."
    else:
        next_run = reminders.next_occurrence(schedule, reminder.next_run_at, REMINDER_TIMEZONE)
        anchor = date.fromisoformat(reminder.anchor)
        note = "Back to normal after that."
    update_reminder_schedule(reminder.id, schedule, anchor, next_run)
    log.info("[%s] %s skipped a reminder for %r", ctx.guild.name, ctx.author, campaign.alias)
    await send_campaign_reply(ctx, f"⏭️ Skipped the {upcoming:%a %d %b} reminder for **{campaign.alias}**.\n"
                                   f"Next one: {when_text(next_run)}. {note}")


async def campaign_alias_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    typed = current.casefold()
    matches = [c.alias for c in list_campaigns(interaction.guild_id) if typed in c.alias.casefold()]
    return [app_commands.Choice(name=alias, value=alias) for alias in matches[:25]]


for _command in (campaign_show, campaign_edit, campaign_remove, campaign_remind, campaign_unremind,
                 campaign_reschedule, campaign_skip):
    _command.autocomplete("alias")(campaign_alias_autocomplete)


@bot.listen("on_raw_reaction_add")
async def reminder_subscribe(payload: discord.RawReactionActionEvent):
    if str(payload.emoji) != REMINDER_EMOJI or payload.user_id == bot.user.id:
        return
    reminder = reminder_for_message(payload.message_id)
    if reminder:
        subscribe(reminder.id, payload.user_id)
        log.info("Someone subscribed to reminder %d", reminder.id)


@bot.listen("on_raw_reaction_remove")
async def reminder_unsubscribe(payload: discord.RawReactionActionEvent):
    if str(payload.emoji) != REMINDER_EMOJI:
        return
    reminder = reminder_for_message(payload.message_id)
    if reminder:
        unsubscribe(reminder.id, payload.user_id)
        log.info("Someone unsubscribed from reminder %d", reminder.id)


async def send_reminder(reminder: Reminder) -> None:
    campaign = get_campaign(reminder.guild_id, reminder.alias_key)
    if campaign is None:
        delete_reminder(reminder.guild_id, reminder.alias_key)
        return
    channel = bot.get_channel(reminder.channel_id)
    if channel is None:
        log.warning("Reminder %d: can't find channel %s", reminder.id, reminder.channel_id)
        return
    people = subscribers(reminder.id)
    pings = " ".join(f"<@{user_id}>" for user_id in people)
    content = f"⏰ **{campaign.alias}** is coming up! {pings}".strip()
    if not people:
        content += f"\n-# Nobody's subscribed yet. React {REMINDER_EMOJI} to the reminder setup message to get pinged."
    await channel.send(content, embed=campaign_embed(campaign), view=campaign_buttons(campaign),
                       allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=u) for u in people],
                                                                everyone=False, roles=False))


@tasks.loop(seconds=30)
async def reminder_loop():
    now = datetime.now(timezone.utc)
    for reminder in due_reminders(now):
        try:
            if now - reminder.next_run_at <= REMINDER_GRACE:
                await send_reminder(reminder)
                log.info("Sent reminder %d", reminder.id)
            else:
                log.warning("Skipped reminder %d: it was due at %s, too long ago", reminder.id, reminder.next_run)
        except discord.HTTPException as error:
            log.warning("Couldn't send reminder %d: %s", reminder.id, error)
        finally:
            # Always move on to the next occurrence, so a failure can't cause repeated pings.
            if get_reminder(reminder.guild_id, reminder.alias_key):
                anchor = date.fromisoformat(reminder.anchor)
                set_next_run(reminder.id, reminders.next_occurrence(reminder.schedule, now, REMINDER_TIMEZONE, anchor))


@reminder_loop.before_loop
async def before_reminder_loop():
    await bot.wait_until_ready()


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
            prefix = COMMAND_PREFIX if sub.extras.get("prefix_only") else "/"
            embed.add_field(name=f"{prefix}{sub.qualified_name} {sub.signature}".strip(), value=sub.description, inline=False)
    if command.name == "quote":
        embed.add_field(
            name="More ways to save a quote",
            value=(
                f"• **Reply** to a message with `{COMMAND_PREFIX}quote` to save it, or `{COMMAND_PREFIX}quote @someone` "
                "to credit someone else (handy when a person types out what someone said in voice).\n"
                f"• **Type it:** `{COMMAND_PREFIX}quote @someone what they said`. Add ` -- context` on the end for context.\n"
                "• **Right-click a message** → Apps → **Save quote** to edit the wording and pick who said it "
                "(clear the picker to save it anonymously).\n"
                f"• **Anonymous:** leave `user` empty in `/quote add`, or use `{COMMAND_PREFIX}quote anon` "
                "(which also works as a reply). "
                "`/quote dissociate <#>` takes the name off an existing quote, and `/quote claim <#>` "
                "lets you put your own name back on an anonymous one.\n"
                f"• `{COMMAND_PREFIX}quote` on its own gives a random quote; `{COMMAND_PREFIX}quote 12` shows quote #12."
            ),
            inline=False,
        )
    if command.name == "campaign":
        embed.add_field(
            name="Tips",
            value=(
                "• Aliases can be anything: `Monday game`, `Curse of Strahd`, `the cursed one`. In the slash commands, "
                "start typing and Discord suggests them.\n"
                f"• `{COMMAND_PREFIX}campaign Monday game` shows one; `{COMMAND_PREFIX}campaign` lists them all.\n"
                f"• With `{COMMAND_PREFIX}campaign add`, put a multi-word alias in quotes: "
                f"`{COMMAND_PREFIX}campaign add \"Monday game\" <D&D Beyond link> <VTT link>`.\n"
                f"• To remove one link, `/campaign edit` it to `{CLEAR_LINK}`.\n"
                "• **Reminders:** `/campaign remind Monday game mondays at 1800` (also `monday 6pm`, "
                "`mondays and thursdays at 7pm`, `every other friday at 7:30pm from 23 oct`). "
                f"React {REMINDER_EMOJI} to the message it posts to get pinged; `/campaign unremind` stops it. "
                f"Times are {REMINDER_TIMEZONE.key} time.\n"
                "• **Game moved?** `/campaign skip` skips the next one (fortnightly games shift a week). "
                "`/campaign reschedule` with `next 26 oct` sets the next session's date, or give a new schedule. "
                f"Both keep everyone's {REMINDER_EMOJI}."
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
        usage = (" | ".join(sorted(sub.name for sub in command.commands if not sub.extras.get("prefix_only")))
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
