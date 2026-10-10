"""Shared test setup: a fresh in-memory database and a fake bot for every test.

Run the tests with:  python -m pytest
"""

import os

# Before importing ktdi: never read the real .env, and don't pick up library settings from the environment.
os.environ["KTDI_NO_DOTENV"] = "1"
for name in ("CALIBRE_URL", "BOOKS_GUILD_IDS", "GUILD_IDS", "COMMAND_PREFIX", "REMINDER_TIMEZONE", "BOT_TIMEZONE",
             "ANIME_USER_ID", "LINUX_HATER_ID", "WHOSPRAY_ADMIN_IDS", "DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN",
             "RPG_DROPBOX_PATH", "RPG_GUILD_IDS", "SPRAY_RATE_TIME"):
    os.environ.pop(name, None)

import pytest  # noqa: E402

from ktdi import common, db  # noqa: E402
from ktdi.features import books, fun, rpg  # noqa: E402
from tests.fakes import FakeBot  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_state():
    db.init(":memory:")
    fun.recent_speakers.clear()
    fun.last_blame.clear()
    books.recent_books.clear()
    rpg.recent_files.clear()
    common.bot = FakeBot()
    yield
    db.conn.close()


@pytest.fixture
def bot() -> FakeBot:
    return common.bot


@pytest.fixture
def clock(monkeypatch):
    """Freeze datetime.now() in the given modules: clock.set(dt, module, ...)."""
    from tests.fakes import FrozenClock
    frozen = FrozenClock(monkeypatch)
    return frozen
