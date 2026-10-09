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


def test_upgrades_a_movies_table_from_before_the_watchlist(tmp_path):
    from ktdi.features import movie
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE movies (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,"
                " title TEXT NOT NULL, set_by INTEGER NOT NULL, created_at TEXT NOT NULL, started_at TEXT,"
                " paused_at TEXT, paused_seconds INTEGER NOT NULL DEFAULT 0, ended_at TEXT)")
    old.execute("INSERT INTO movies (guild_id, title, set_by, created_at, started_at, ended_at) VALUES"
                " (111, 'Alien', 1, '2026-10-01T19:00:00+00:00', '2026-10-01T19:05:00+00:00',"
                " '2026-10-01T21:00:00+00:00')")
    old.execute("INSERT INTO movies (guild_id, title, set_by, created_at) VALUES"
                " (111, 'Jaws', 1, '2026-10-02T19:00:00+00:00')")  # lined up, never started
    old.commit()
    old.close()

    db.init(path)
    alien = movie.find_watched(111, "alien")
    assert alien.watch_number == 1 and alien.archived_at is None
    assert movie.next_watch_number(111, "Alien") == 2  # an old watch counts towards the next number
    assert movie.current_movie(111).title == "Jaws" and movie.current_movie(111).watch_number is None
    assert movie.current_movie(111).link is None and movie.watchlist(111) == []  # to-watch list columns added
    db.conn.close()


def test_upgrades_spray_futures_from_before_hours_and_interest(tmp_path):
    from ktdi.features import fun
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE spray_futures (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,"
                " channel_id INTEGER NOT NULL, bettor_id INTEGER NOT NULL, target_id INTEGER NOT NULL,"
                " stake INTEGER NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, settled_at TEXT,"
                " outcome TEXT, paid INTEGER NOT NULL DEFAULT 0, sprayed_by INTEGER)")
    old.execute("INSERT INTO spray_futures (guild_id, channel_id, bettor_id, target_id, stake, created_at, expires_at,"
                " settled_at, outcome) VALUES (111, 500, 1, 2, 3, 'x', 'x', 'x', 'lost')")
    old.commit()
    old.close()

    db.init(path)
    assert db.conn.execute("SELECT hours, rate, amount FROM spray_futures").fetchone() == (1, 0, 3)
    assert fun.get_spray_count(111, 1) == 3  # an old lost bet still counts its stake
    db.conn.close()
