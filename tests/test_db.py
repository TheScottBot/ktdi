"""Opening older databases: upgrades add what's missing and keep existing data (ktdi.db)."""

import sqlite3

from ktdi import db


def test_upgrades_an_older_database(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE guild_settings (guild_id INTEGER PRIMARY KEY, shared_state INTEGER NOT NULL)")
    old.execute("INSERT INTO guild_settings VALUES (333, 0)")
    old.execute("CREATE TABLE campaign_reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,"
                " alias_key TEXT NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER, days TEXT NOT NULL,"
                " time TEXT NOT NULL, every_weeks INTEGER NOT NULL, anchor TEXT NOT NULL, next_run TEXT NOT NULL,"
                " created_by INTEGER NOT NULL, UNIQUE (guild_id, alias_key))")
    old.commit()
    old.close()

    db.init(path)
    assert not db.is_shared(333)  # existing setting kept
    assert db.whospray_user(333) is None  # new column added, empty
    db.set_whospray_user(333, 2)
    assert db.whospray_user(333) == 2 and not db.is_shared(333)
    columns = [c[1] for c in db.conn.execute("PRAGMA table_info(campaign_reminders)")]
    assert "lead_minutes" in columns
    db.conn.close()
