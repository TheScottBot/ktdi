"""Settings from .env (or .env.dev with --dev). Relative paths are resolved from the repo root."""

import logging
import os
import sys
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

DB_PATH = str(BASE_DIR / os.getenv("DB_PATH", "ktdi.db"))
# Rolling log file. Rotates at LOG_MAX_BYTES, keeping LOG_BACKUPS old files.
LOG_FILE = BASE_DIR / os.getenv("LOG_FILE", "logs/ktdi-dev.log" if DEV else "logs/ktdi.log")
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
# Who may choose the Don (/settings whospray_user). Nobody else can, not even server admins. Empty = nobody.
WHOSPRAY_ADMIN_IDS = parse_ids("WHOSPRAY_ADMIN_IDS")
# The /linux target (@poltergeis.t).
LINUX_HATER_ID = os.getenv("LINUX_HATER_ID") or "351350774435151873"
