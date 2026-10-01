"""The SQLite database: connection, tables, upgrades, and shared state.

Call init() once at startup (the tests call it with ":memory:"). Everything else uses db.conn.
"""

import sqlite3

conn: sqlite3.Connection = None  # type: ignore[assignment]  # Set by init().

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS sprays (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        count    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bribes (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        count    INTEGER NOT NULL DEFAULT 0,
        total    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS briber_role_holders (
        guild_id INTEGER PRIMARY KEY,
        user_id  INTEGER NOT NULL
    )
    """,
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
    """,
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
    """,
    """
    CREATE TABLE IF NOT EXISTS campaign_reminders (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id    INTEGER NOT NULL,
        alias_key   TEXT NOT NULL,     -- the campaign it belongs to (one reminder per campaign)
        channel_id  INTEGER NOT NULL,  -- where the reminders are posted
        message_id  INTEGER,           -- the setup message people react 🔔 to
        days        TEXT NOT NULL,     -- "0,3" = Mondays and Thursdays
        time        TEXT NOT NULL,     -- the game's start time, e.g. "19:00", in REMINDER_TIMEZONE
        every_weeks INTEGER NOT NULL,  -- 1 weekly, 2 fortnightly
        anchor      TEXT NOT NULL,     -- a date in an "on" week, for fortnightly schedules
        next_run    TEXT NOT NULL,     -- when the next ping goes out (start time minus lead_minutes), ISO 8601 UTC
        created_by  INTEGER NOT NULL,
        UNIQUE (guild_id, alias_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS campaign_reminder_subscribers (
        reminder_id INTEGER NOT NULL,
        user_id     INTEGER NOT NULL,
        PRIMARY KEY (reminder_id, user_id)
    )
    """,
    "CREATE TABLE IF NOT EXISTS guild_settings (guild_id INTEGER PRIMARY KEY, shared_state INTEGER NOT NULL)",
    """
    CREATE TABLE IF NOT EXISTS don_orders (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        count    INTEGER NOT NULL DEFAULT 0,  -- times the Don made them spray themselves (/tdoi)
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spray_expunges (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        count    INTEGER NOT NULL DEFAULT 0,  -- sprays bribed off their record (/expunge); subtracted from sprays
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spray_bails (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,  -- whose spray was removed
        paid_by  INTEGER NOT NULL,  -- who paid (/bail)
        count    INTEGER NOT NULL DEFAULT 0,  -- subtracted from user_id's sprays
        PRIMARY KEY (guild_id, user_id, paid_by)
    )
    """,
]


def _columns(table: str) -> list[str]:
    return [column[1] for column in conn.execute(f"PRAGMA table_info({table})")]


def _upgrade() -> None:
    """Changes to tables that already existed in older databases."""
    # How many minutes before the start time to ping. Existing reminders get 0 (ping at the time given).
    if "lead_minutes" not in _columns("campaign_reminders"):
        conn.execute("ALTER TABLE campaign_reminders ADD COLUMN lead_minutes INTEGER NOT NULL DEFAULT 0")
    # Who /whospray asks, per server. Unset until someone chooses.
    if "whospray_user_id" not in _columns("guild_settings"):
        conn.execute("ALTER TABLE guild_settings ADD COLUMN whospray_user_id INTEGER")


def init(path: str) -> None:
    global conn
    conn = sqlite3.connect(path)
    for statement in SCHEMA:
        conn.execute(statement)
    _upgrade()
    conn.commit()
    shared_state.clear()
    shared_state.update(
        {guild_id: bool(shared) for guild_id, shared in conn.execute("SELECT guild_id, shared_state FROM guild_settings")}
    )


# --- Shared state: which servers pool their quotes, sprays, bribes and campaigns ---
# Every row keeps the server it came from. Reads use scope(): an isolated server sees only its own rows,
# a shared server sees every row except those from isolated servers. Switching back and forth loses nothing.
# A server that has never set it is shared.
shared_state: dict[int, bool] = {}


def is_shared(guild_id: int) -> bool:
    return shared_state.get(guild_id, True)


def set_shared(guild_id: int, shared: bool) -> None:
    conn.execute("INSERT INTO guild_settings (guild_id, shared_state) VALUES (?, ?)"
                 " ON CONFLICT (guild_id) DO UPDATE SET shared_state = excluded.shared_state", (guild_id, int(shared)))
    conn.commit()
    shared_state[guild_id] = shared


def whospray_user(guild_id: int) -> int | None:
    """Who /whospray asks on this server (a per-server setting, never shared)."""
    row = conn.execute("SELECT whospray_user_id FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()
    return row[0] if row else None


def set_whospray_user(guild_id: int, user_id: int | None) -> None:
    conn.execute("INSERT INTO guild_settings (guild_id, shared_state, whospray_user_id) VALUES (?, ?, ?)"
                 " ON CONFLICT (guild_id) DO UPDATE SET whospray_user_id = excluded.whospray_user_id",
                 (guild_id, int(is_shared(guild_id)), user_id))
    conn.commit()


def scope(guild_id: int) -> tuple[str, list[int]]:
    """The WHERE condition (and its parameters) for the rows this server can see."""
    if not is_shared(guild_id):
        return "guild_id = ?", [guild_id]
    isolated = [g for g, shared in shared_state.items() if not shared]
    if not isolated:
        return "1 = 1", []
    return f"guild_id NOT IN ({', '.join('?' * len(isolated))})", isolated
