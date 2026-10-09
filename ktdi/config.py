"""Settings from .env (or .env.dev with --dev). Relative paths are resolved from the repo root."""

import logging
import os
import sys
from datetime import time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Run with --dev (e.g. "python bot.py --dev") to use the dev bot's settings in .env.dev.
DEV = "--dev" in sys.argv
ENV_FILE = ".env.dev" if DEV else ".env"
if not os.getenv("KTDI_NO_DOTENV"):  # The tests set this so they never read your real .env.
    load_dotenv(BASE_DIR / ENV_FILE)


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


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
# Comma-separated server IDs to register slash commands to (GUILD_ID also accepted).
GUILD_IDS = parse_ids("GUILD_IDS", "GUILD_ID")

# Calibre-Web library for /books. The commands only work in BOOKS_GUILD_IDS, and only if CALIBRE_URL is set.
BOOKS_GUILD_IDS = parse_ids("BOOKS_GUILD_IDS")
CALIBRE_URL = os.getenv("CALIBRE_URL")
CALIBRE_USERNAME = os.getenv("CALIBRE_USERNAME", "")
CALIBRE_PASSWORD = os.getenv("CALIBRE_PASSWORD", "")
BOOK_FORMATS = [f for f in (os.getenv("BOOK_FORMATS") or "epub,kepub,azw3,mobi,pdf,cbz").replace(" ", "").split(",") if f]

# RPG rulebooks in a Dropbox folder, for /rpg. Only in RPG_GUILD_IDS, and only if all the DROPBOX_* values are set
# (a Dropbox app with read-only access; see the README for setting one up).
RPG_GUILD_IDS = parse_ids("RPG_GUILD_IDS")
DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY", "")
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET", "")
DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN", "")
RPG_DROPBOX_PATH = os.getenv("RPG_DROPBOX_PATH", "")  # The folder, as in your Dropbox: e.g. /Family Room/RPGs

DB_PATH = str(BASE_DIR / os.getenv("DB_PATH", "ktdi.db"))
# Rolling log file. Rotates at LOG_MAX_BYTES, keeping LOG_BACKUPS old files.
LOG_FILE = BASE_DIR / os.getenv("LOG_FILE", "logs/ktdi-dev.log" if DEV else "logs/ktdi.log")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 1_000_000))
LOG_BACKUPS = int(os.getenv("LOG_BACKUPS", 5))

def zone_setting(name: str, default: ZoneInfo | str) -> ZoneInfo:
    """An IANA timezone name from .env, e.g. Europe/London (summer time handled)."""
    value = os.getenv(name)
    if not value:
        return default if isinstance(default, ZoneInfo) else ZoneInfo(default)
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        logging.getLogger("ktdi").warning("Unknown %s %r, using UTC.", name, value)
        return ZoneInfo("UTC")


# The bot's own timezone: what "now" means in /timezone convert when you leave out the zones and haven't set yours.
BOT_TIMEZONE = zone_setting("BOT_TIMEZONE", "Europe/London")
# Timezone that campaign reminder times are in, e.g. "mondays at 1800" means 18:00 here. Defaults to BOT_TIMEZONE.
REMINDER_TIMEZONE = zone_setting("REMINDER_TIMEZONE", BOT_TIMEZONE)


def time_setting(name: str, default: str) -> dt_time:
    """A time of day from .env, as HH:MM (24-hour)."""
    value = os.getenv(name) or default
    try:
        return dt_time.fromisoformat(value)
    except ValueError:
        logging.getLogger("ktdi").warning("%s %r isn't a time like 00:00; using %s.", name, value, default)
        return dt_time.fromisoformat(default)


# When each day's spray interest rate (/sprayfutures, /sprayrate) is set, in BOT_TIMEZONE. Defaults to midnight.
SPRAY_RATE_TIME = time_setting("SPRAY_RATE_TIME", "00:00")

# Optional role given to each server's biggest briber. Skipped on servers without a role by this name.
BRIBER_ROLE_NAME = os.getenv("BRIBER_ROLE_NAME", "Champion Briber")
# Who may choose the Don (/settings whospray_user). Nobody else can, not even server admins. Empty = nobody.
WHOSPRAY_ADMIN_IDS = parse_ids("WHOSPRAY_ADMIN_IDS")
# Who /anime asks about a random anime (a user ID). Unset = /anime says it isn't set up.
ANIME_USER_ID = next(iter(parse_ids("ANIME_USER_ID")), None)
# The /linux target (our Linux hater).
LINUX_HATER_ID = os.getenv("LINUX_HATER_ID") or "000000000000000000"
