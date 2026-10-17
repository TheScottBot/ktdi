"""Movie night: /nowplaying (set, start, pause, sync, end, history), /shhh, /nowplaying rate, /nowplaying predict and
/nowplaying bingo.

A server has at most one current movie: its newest row in `movies` with no ended_at. It's lined up with /nowplaying set,
and nothing starts until /nowplaying start, which starts it at once with a big GO (a countdown didn't keep people in
step: some only saw it at GO), and carries on after a pause the same way. Ending it reveals the predictions (people
react ✅/❌ to judge them) and asks for ratings. Bingo cards aren't stored: each is shuffled from a seed of (movie,
person), so it's the same every time.

And what the group does to the film: /nowplaying objection (timestamped, ruled on by the committee), /nowplaying canon
(alternative canon, voted in with ✅/❌ and kept against the title, so it's read out on every rewatch) and the
committee's official report on a finished watch (/nowplaying history <film>).

Discord lists every slash subcommand as its own line, so related ones are one slash subcommand with an option
(/nowplaying sync [time] is elapsed and sct; bingo card [square] [unmark] is card, mark and unmark). The old ones are
still typed (!np resume, !np sct 1:07:30, !np bingo mark 7): with_app_command=False, and extras["merged_into"] names
where they went, for /help.
"""

import asyncio
import math
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import common, db
from ktdi.common import NO_PINGS, log, plural
from ktdi.lib import fuzzy, letterboxd

HELP_CATEGORY = "🎬 Movie night"
TITLE_MAX_LENGTH = 100
TEXT_MAX_LENGTH = 200
HISTORY_SHOWN = 10
LONG_PAUSE_SECONDS = 5 * 60
SYNC_LEAD_SECONDS = 10  # /nowplaying sync: time to skip to the spot before pressing play.
CALLED_IT, NOT_IT = "✅", "❌"

SHHH_LINES = [
    "Quiet, please. This bit matters.",
    "Everyone hush. Eyes on the screen.",
    "Phones down, mouths shut.",
    "Save it for the credits.",
    "Whatever you were about to type, hold that thought.",
    "This is the good bit. Silence.",
    "The committee requests absolute silence.",
    "Not now. Watch.",
]

SHHH_DURING_LINES = [
    "Quiet, please. This bit of **{title}** matters.",
    "Everyone hush. **{title}** is getting good.",
    "Save it for the credits of **{title}**.",
    "Shhh. **{title}** is trying to tell us something.",
]

LONG_PAUSE_LINES = [
    "The committee notes this was meant to be a five-minute break.",
    "The committee would like to know what took so long.",
    "The committee has started the clock on future intermissions.",
]

CANON_SHOWN = 5  # Established canon listed when a film starts again.
SUSTAINED_ONE_IN = 6  # The committee sustains about one objection in six.
OBJECTIONS_SHOWN = 5  # In the committee's report.

OVERRULED_LINES = [
    "The committee has determined that this is, in fact, a film. Objection overruled.",
    "Overruled. The characters can't hear you.",
    "Overruled. That's the plot.",
    "Overruled. Nobody in this film has ever seen a film.",
    "Overruled. The committee is enjoying it.",
    "Noted, and ignored. Overruled.",
    "Overruled. If they did the sensible thing, it'd be a much shorter film.",
    "Overruled. The committee has seen worse decisions in this server.",
]
SUSTAINED_LINES = [
    "Sustained. The committee also has questions.",
    "Sustained. Nobody would do that.",
    "Sustained. The committee will be writing to the director.",
    "Sustained. Strike that scene from the record.",
]
REPORT_FINDINGS = [
    "The crew demonstrated a concerning disregard for workplace safety.",
    "Nobody in this film has read a risk assessment.",
    "Too many people went off on their own.",
    "Communication between characters was found to be inadequate.",
    "The plot was found to be broadly present.",
    "The committee notes several decisions it would not have made.",
    "The committee was not consulted on the casting.",
    "The film ran for approximately the length of a film.",
]
REPORT_RECOMMENDATIONS = [
    "Mandatory training before viewing the sequel.",
    "No further action.",
    "A strongly worded letter to the director.",
    "More snacks next time.",
    "Rewatch it with the subtitles on.",
    "Everyone to have a little think about what they've done.",
    "A sequel nobody asked for.",
    "Refer the matter to a subcommittee.",
]

BINGO_FREE_SPACE = "Free space: snacks"
BINGO_SQUARES = [
    "Someone says the film's title",
    "A hero walks away from an explosion",
    "\"We're not so different, you and I\"",
    "A phone has no signal at the worst moment",
    "\"I've got a bad feeling about this\"",
    "A slow clap",
    "Someone says \"Let's split up\"",
    "A dramatic slow-motion walk",
    "The villain explains their plan",
    "Someone survives a fall they really shouldn't",
    "A training montage",
    "\"It's quiet. Too quiet.\"",
    "Someone ends up in water they didn't plan to",
    "A car won't start",
    "A countdown stopped with seconds to spare",
    "A kiss in the rain",
    "Someone yells \"Nooooo!\"",
    "A jump scare in a mirror",
    "An animal saves the day",
    "Two characters turn out to be related",
    "Someone says \"Trust me\"",
    "A sequel is clearly being set up",
    "Someone here says a line before the film does",
    "Someone here checks their phone",
    "Someone here asks \"wait, who's that?\"",
    "A betrayal",
    "Hacking by typing very fast",
    "\"Enhance\" on a blurry photo",
    "The wise old mentor dies",
    "A dream sequence",
    "A flashback",
    "A song everyone knows",
    "Someone here screams",
    "Someone dramatically takes off their sunglasses",
    "A last-second rescue",
    "A cameo someone here recognises",
    "Someone here falls asleep",
    "A dramatic \"we need to talk\"",
    "Someone gets a dramatic phone call",
    "The power goes out",
]
BINGO_SIZE = 5
BINGO_FREE = 13  # The middle square.
BINGO_LINES = ([[r * BINGO_SIZE + c + 1 for c in range(BINGO_SIZE)] for r in range(BINGO_SIZE)]
               + [[r * BINGO_SIZE + c + 1 for r in range(BINGO_SIZE)] for c in range(BINGO_SIZE)]
               + [[i * BINGO_SIZE + i + 1 for i in range(BINGO_SIZE)]]
               + [[i * BINGO_SIZE + (BINGO_SIZE - i) for i in range(BINGO_SIZE)]])


@dataclass
class Movie:
    id: int
    guild_id: int
    title: str
    set_by: int
    created_at: datetime
    started_at: datetime | None
    paused_at: datetime | None
    paused_seconds: int
    ended_at: datetime | None
    archived_at: datetime | None  # Set aside before it started: on the watchlist, not yet watched.
    watch_number: int | None  # 1 for the first time we watched this title, 2 for the second...; set by /nowplaying start.
    link: str | None  # Its Letterboxd page, if it was imported from a list.
    dropped_at: datetime | None  # Taken off the watchlist.
    struck_at: datetime | None  # Struck off the watchlist as watched: still listed (crossed out), left out of votes.
    from_watchlist: bool  # Lined up from the watchlist, so it goes back on it, struck off, when it ends.

    @property
    def name(self) -> str:
        return discord.utils.escape_markdown(self.title)

    @property
    def linked_name(self) -> str:
        """The name, linked to its Letterboxd page if it has one (<> stops Discord adding a big preview)."""
        return f"[{self.name}](<{self.link}>)" if self.link else self.name

    @property
    def label(self) -> str:
        """The name, plus which watch it is if we've seen it before: Alien (watch #2)."""
        number = self.watch_number or next_watch_number(self.guild_id, self.title)
        return f"{self.name} (watch #{number})" if number > 1 else self.name


def plain_label(movie: Movie) -> str:
    """Movie.label without markdown escaping, for embed titles (which don't render markdown)."""
    number = movie.watch_number or next_watch_number(movie.guild_id, movie.title)
    return f"{movie.title} (watch #{number})" if number > 1 else movie.title


MOVIE_COLUMNS = ("id, guild_id, title, set_by, created_at, started_at, paused_at, paused_seconds, ended_at, "
                 "archived_at, watch_number, link, dropped_at, struck_at, from_watchlist")
YEAR_RE = re.compile(r"\s*\(\d{4}\)$")


def title_key(title: str) -> str:
    """Titles match whatever the capitals or spacing: "the  THING" is "The Thing"."""
    return " ".join(title.split()).casefold()


def without_year(title: str) -> str:
    """"Alien (1979)" -> "alien": so typing "Alien" finds an imported "Alien (1979)"."""
    return YEAR_RE.sub("", title_key(title))


def now() -> datetime:
    return datetime.now(timezone.utc)


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _movie(row) -> Movie | None:
    if row is None:
        return None
    (id_, guild_id, title, set_by, created, started, paused, paused_seconds, ended, archived, watch_number, link,
     dropped, struck, from_watchlist) = row
    return Movie(id_, guild_id, title, set_by, _time(created), _time(started), _time(paused), paused_seconds,
                 _time(ended), _time(archived), watch_number, link, _time(dropped), _time(struck), bool(from_watchlist))


def one_line(text: str | None, limit: int = TEXT_MAX_LENGTH) -> str:
    return " ".join((text or "").split())[:limit]


# --- Movies ---
def current_movie(guild_id: int) -> Movie | None:
    """This server's movie that hasn't ended and isn't on the watchlist: lined up, playing or paused."""
    return _movie(db.conn.execute(f"SELECT {MOVIE_COLUMNS} FROM movies WHERE guild_id = ? AND ended_at IS NULL "
                                  "AND archived_at IS NULL ORDER BY id DESC LIMIT 1", (guild_id,)).fetchone())


def get_movie(movie_id: int) -> Movie | None:
    return _movie(db.conn.execute(f"SELECT {MOVIE_COLUMNS} FROM movies WHERE id = ?", (movie_id,)).fetchone())


def movie_to_rate(guild_id: int) -> Movie | None:
    """The one playing, or else the last one that finished."""
    return _movie(db.conn.execute(f"SELECT {MOVIE_COLUMNS} FROM movies WHERE guild_id = ? AND started_at IS NOT NULL "
                                  "ORDER BY started_at DESC, id DESC LIMIT 1", (guild_id,)).fetchone())


def next_watch_number(guild_id: int, title: str) -> int:
    """Which watch of this title starting now would be (across shared servers)."""
    where, params = db.scope(guild_id)
    watched = db.conn.execute(f"SELECT COUNT(*) FROM movies WHERE {where} AND title_key = ? AND started_at IS NOT NULL",
                              (*params, title_key(title))).fetchone()[0]
    return watched + 1


def watchlist(guild_id: int) -> list[Movie]:
    """Not yet watched: films set aside before they started, added, or imported. Newest first, but an imported list
    keeps its own order, and struck-off films go last. Per server, like the current film."""
    rows = db.conn.execute(f"SELECT {MOVIE_COLUMNS} FROM movies WHERE guild_id = ? AND archived_at IS NOT NULL "
                           "AND dropped_at IS NULL ORDER BY struck_at IS NOT NULL, archived_at DESC, id",
                           (guild_id,)).fetchall()
    return [_movie(row) for row in rows]


def find_on_watchlist(guild_id: int, title: str) -> Movie | None:
    """By exact title, or else by title without the year if only one matches ("Alien" finds "Alien (1979)")."""
    saved = watchlist(guild_id)
    exact = next((m for m in saved if title_key(m.title) == title_key(title)), None)
    if exact:
        return exact
    loose = [m for m in saved if without_year(m.title) == without_year(title)]
    return loose[0] if len(loose) == 1 else None


def add_to_watchlist(guild_id: int, title: str, user_id: int, link: str | None = None) -> Movie | None:
    """A new film for the watchlist, or None if it's already on it."""
    if any(title_key(m.title) == title_key(title) for m in watchlist(guild_id)):
        return None
    moment = now().isoformat()
    cursor = db.conn.execute("INSERT INTO movies (guild_id, title, title_key, set_by, created_at, archived_at, link) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (guild_id, title, title_key(title), user_id, moment, moment, link))
    db.conn.commit()
    return get_movie(cursor.lastrowid)


def keep_on_watchlist_struck(movie: Movie) -> None:
    """A film lined up from the watchlist has just been watched: it goes back on the list, struck off. (Its watch
    keeps the ratings and predictions; this is a fresh entry, ready to line up again for a rewatch.)"""
    moment = now().isoformat()
    existing = next((m for m in watchlist(movie.guild_id) if title_key(m.title) == title_key(movie.title)), None)
    if existing:  # Someone added it again meanwhile: strike that one.
        if not existing.struck_at:
            _update(existing.id, struck_at=moment)
        return
    db.conn.execute("INSERT INTO movies (guild_id, title, title_key, set_by, created_at, archived_at, link, struck_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (movie.guild_id, movie.title, title_key(movie.title), movie.set_by, moment, moment, movie.link,
                     moment))
    db.conn.commit()


def sealed_count(movie_id: int) -> int:
    return db.conn.execute("SELECT COUNT(*) FROM movie_predictions WHERE movie_id = ?", (movie_id,)).fetchone()[0]


def archive(movie: Movie) -> str:
    """Put a film that never started on the watchlist, keeping its predictions. Returns a note saying so."""
    _update(movie.id, archived_at=now())
    sealed = sealed_count(movie.id)
    kept = f" with its {plural(sealed, 'sealed prediction')}" if sealed else ""
    return f"{movie.name} is on the watchlist (not yet watched){kept}. `/nowplaying set {movie.title}` brings it back."


def line_up(guild_id: int, title: str, user_id: int) -> tuple[Movie, bool]:
    """Line up a title: back from the watchlist (predictions and all) if it's there, otherwise new.
    Returns the film and whether it came off the watchlist."""
    saved = find_on_watchlist(guild_id, title)
    if saved:
        if title_key(saved.title) != title_key(title):
            title = saved.title  # Found without the year: keep the fuller "Alien (1979)".
        _update(saved.id, archived_at=None, title=title, title_key=title_key(title), set_by=user_id, from_watchlist=1)
        return get_movie(saved.id), True
    cursor = db.conn.execute("INSERT INTO movies (guild_id, title, title_key, set_by, created_at) VALUES (?, ?, ?, ?, ?)",
                             (guild_id, title, title_key(title), user_id, now().isoformat()))
    db.conn.commit()
    return get_movie(cursor.lastrowid), False


def _update(movie_id: int, **values) -> None:
    columns = ", ".join(f"{name} = ?" for name in values)
    stored = [v.isoformat() if hasattr(v, "isoformat") else v for v in values.values()]
    db.conn.execute(f"UPDATE movies SET {columns} WHERE id = ?", (*stored, movie_id))
    db.conn.commit()


def watched_seconds(movie: Movie) -> int:
    if movie.started_at is None:
        return 0
    until = movie.ended_at or movie.paused_at or now()
    return max(int((until - movie.started_at).total_seconds()) - movie.paused_seconds, 0)


def duration(seconds: int) -> str:
    hours, minutes = divmod(seconds // 60, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m" if minutes else "under a minute"


def timecode(seconds: int) -> str:
    """Where the film is, like a player shows it: 1:07:42. Handy for everyone scrubbing to the same spot."""
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}"


TIMECODE_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")
TIME_PART_RE = re.compile(r"(\d+)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)")  # Longest first.
TIMECODE_EXAMPLES = "`1:07:30`, `47:30`, `1h 7m`, `47m` or `47` (minutes)"
TIMECODE_MAX = 12 * 60 * 60


def parse_timecode(text: str) -> int | None:
    """Seconds into the film, from 1:07:30, 47:30, 1h 7m 30s, 47m or 47 (minutes); None if it isn't one."""
    text = " ".join(text.lower().split())
    if text.isdigit():
        seconds = int(text) * 60
    elif match := TIMECODE_RE.match(text):
        hours, minutes, secs = int(match.group(1) or 0), int(match.group(2)), int(match.group(3))
        if secs > 59 or (match.group(1) and minutes > 59):
            return None
        seconds = hours * 3600 + minutes * 60 + secs
    else:
        parts = TIME_PART_RE.findall(text)
        if not parts or TIME_PART_RE.sub("", text).strip(" ,") != "":
            return None
        seconds = sum(int(n) * {"h": 3600, "m": 60, "s": 1}[unit[0]] for n, unit in parts)
    return seconds if seconds <= TIMECODE_MAX else None


def live(moment: datetime) -> str:
    """A timestamp Discord shows as "3 minutes ago" and keeps up to date by itself, for everyone."""
    return f"<t:{int(moment.timestamp())}:R>"


def film_clock(movie: Movie) -> str:
    """The film's running time, ticking live. Pauses are skipped by starting the clock that much later."""
    clock_start = movie.started_at + timedelta(seconds=movie.paused_seconds)
    return f"⏱️ Started {live(clock_start)}" + (", not counting pauses" if movie.paused_seconds else "")


def status_text(movie: Movie | None) -> str:
    if movie is None:
        return "🎬 Nothing's lined up. Pick something with `/nowplaying set <title>`."
    if movie.started_at is None:
        label = f"[{movie.label}](<{movie.link}>)" if movie.link else movie.label
        return f"🎬 **Up next:** {label}\n-# Lined up by <@{movie.set_by}>. `/nowplaying start` when everyone's ready."
    if movie.paused_at:
        return (f"⏸️ **Paused:** {movie.label} at {timecode(watched_seconds(movie))}\n"
                f"-# Paused {live(movie.paused_at)}. `/nowplaying start` to carry on.")
    return f"▶️ **Now playing:** {movie.label}\n-# {film_clock(movie)}. Put on by <@{movie.set_by}>."


async def set_bot_status(bot: commands.Bot, watching: str | None) -> None:
    # The bot's profile shows "Watching <title>". It's one status across every server, so the latest movie wins.
    activity = discord.Activity(type=discord.ActivityType.watching, name=watching[:128]) if watching else None
    try:
        await bot.change_presence(activity=activity)
    except (AttributeError, discord.HTTPException):
        pass  # Not connected, or Discord said no; the message is what matters.


# --- Ratings ---
def ratings(movie_id: int) -> list[tuple[int, int]]:
    return db.conn.execute("SELECT user_id, score FROM movie_ratings WHERE movie_id = ? ORDER BY score DESC, user_id",
                           (movie_id,)).fetchall()


def rating_summary(movie_id: int) -> str:
    scores = ratings(movie_id)
    if not scores:
        return "No ratings yet."
    average = sum(s for _, s in scores) / len(scores)
    text = f"**{average:.1f}/10** from {plural(len(scores), 'rating')}."
    if len(scores) >= 3:
        # Whoever is furthest from everyone else's average, if they're far enough out to argue about.
        def gap(entry):
            others = [s for u, s in scores if u != entry[0]]
            return abs(entry[1] - sum(others) / len(others))
        user_id, score = max(scores, key=gap)
        if gap((user_id, score)) >= 3:
            text += f"\n-# <@{user_id}> gave it a {score}. <@{user_id}> is wrong."
    return text


# --- Predictions ---
def add_prediction(movie: Movie, user_id: int, text: str) -> None:
    db.conn.execute("INSERT INTO movie_predictions (movie_id, guild_id, user_id, text) VALUES (?, ?, ?, ?)",
                    (movie.id, movie.guild_id, user_id, text))
    db.conn.commit()


def predictions(movie_id: int) -> list[tuple[int, int, str]]:
    return db.conn.execute("SELECT id, user_id, text FROM movie_predictions WHERE movie_id = ? ORDER BY id",
                           (movie_id,)).fetchall()


def prediction_by_message(message_id: int) -> tuple[int, int] | None:
    return db.conn.execute("SELECT id, user_id FROM movie_predictions WHERE message_id = ?", (message_id,)).fetchone()


@dataclass
class Verdict:
    """A revealed prediction and how it was judged. It counts as called if more people said ✅ than ❌."""
    user_id: int
    text: str
    yes: int
    no: int

    @property
    def called(self) -> bool:
        return self.yes > self.no


def _verdicts(where: str, params) -> list[Verdict]:
    rows = db.conn.execute(
        f"""
        SELECT p.user_id, p.text,
               (SELECT COUNT(*) FROM movie_prediction_votes v WHERE v.prediction_id = p.id AND v.vote = 1),
               (SELECT COUNT(*) FROM movie_prediction_votes v WHERE v.prediction_id = p.id AND v.vote = 0)
        FROM movie_predictions p WHERE {where} AND p.message_id IS NOT NULL ORDER BY p.id
        """, params).fetchall()
    return [Verdict(*row) for row in rows]


def revealed_predictions(movie_id: int) -> list[Verdict]:
    """Only revealed ones: a film's predictions stay sealed until its /nowplaying end."""
    return _verdicts("p.movie_id = ?", [movie_id])


def prediction_record(guild_id: int, user_id: int) -> tuple[int, int]:
    """(called it, revealed predictions) for one person."""
    where, params = db.scope(guild_id)
    verdicts = _verdicts(f"{where} AND p.user_id = ?", [*params, user_id])
    return sum(v.called for v in verdicts), len(verdicts)


def watched_movies(guild_id: int, limit: int | None = None) -> list[Movie]:
    """Films that have finished, newest first (across shared servers)."""
    where, params = db.scope(guild_id)
    sql = f"SELECT {MOVIE_COLUMNS} FROM movies WHERE {where} AND ended_at IS NOT NULL ORDER BY ended_at DESC, id DESC"
    if limit:
        sql, params = sql + " LIMIT ?", [*params, limit]
    return [_movie(row) for row in db.conn.execute(sql, params)]


WATCH_SUFFIX_RE = re.compile(r"^(.*?)\s*#(\d+)$")


def find_watched(guild_id: int, query: str | None) -> Movie | None:
    """A finished film by title (exact, then partial), or id:<n> from autocomplete. "Alien #2" is the second watch;
    without a number, the latest watch. No query: the last film watched."""
    movies = watched_movies(guild_id)
    query = one_line(query)
    if not query:
        return movies[0] if movies else None
    if query.startswith("id:") and query[3:].isdigit():
        return next((m for m in movies if m.id == int(query[3:])), None)
    watch = None
    if match := WATCH_SUFFIX_RE.match(query):
        query, watch = match.group(1), int(match.group(2))
    key = title_key(query)
    exact = [m for m in movies if title_key(m.title) == key]
    candidates = exact or [m for m in movies if key in title_key(m.title)]
    if watch is not None:
        candidates = [m for m in candidates if (m.watch_number or 1) == watch]
    return candidates[0] if candidates else None


async def reveal_predictions(channel, movie: Movie) -> None:
    found = predictions(movie.id)
    if not found:
        return
    await channel.send(f"🔮 **The predictions for {movie.label} are in.** React {CALLED_IT} if they called it, "
                       f"{NOT_IT} if they didn't. (You can't judge your own.)")
    for prediction_id, user_id, text in found:
        message = await channel.send(f"🔮 <@{user_id}>: {text}", allowed_mentions=NO_PINGS)
        db.conn.execute("UPDATE movie_predictions SET message_id = ? WHERE id = ?", (message.id, prediction_id))
        db.conn.commit()
        try:
            await message.add_reaction(CALLED_IT)
            await message.add_reaction(NOT_IT)
        except discord.HTTPException:
            pass  # No Add Reactions permission: people can still add them.


# What ✅/❌ reactions vote on: a revealed prediction (called it?) or proposed canon (accept it?).
VOTE_TABLES = {"prediction": ("movie_prediction_votes", "prediction_id"), "canon": ("movie_canon_votes", "canon_id")}


def _vote(payload: discord.RawReactionActionEvent) -> tuple[str, int, int] | None:
    """(what's voted on, its id, vote) if this reaction is someone judging a prediction or proposed canon."""
    emoji = str(payload.emoji)
    if emoji not in (CALLED_IT, NOT_IT) or payload.user_id == common.bot.user.id:
        return None
    kind, found = "prediction", prediction_by_message(payload.message_id)
    if found is None:
        kind, found = "canon", canon_by_message(payload.message_id)
    if found is None or found[1] == payload.user_id:  # Nobody judges their own.
        return None
    return kind, found[0], int(emoji == CALLED_IT)


async def prediction_vote(payload: discord.RawReactionActionEvent):
    """A ✅/❌ on a revealed prediction or proposed canon."""
    if vote := _vote(payload):
        table, column = VOTE_TABLES[vote[0]]
        db.conn.execute(f"INSERT OR IGNORE INTO {table} ({column}, user_id, vote) VALUES (?, ?, ?)",
                        (vote[1], payload.user_id, vote[2]))
        db.conn.commit()


async def prediction_unvote(payload: discord.RawReactionActionEvent):
    if vote := _vote(payload):
        table, column = VOTE_TABLES[vote[0]]
        db.conn.execute(f"DELETE FROM {table} WHERE {column} = ? AND user_id = ? AND vote = ?",
                        (vote[1], payload.user_id, vote[2]))
        db.conn.commit()


# --- Canon and objections ---
@dataclass
class Canon:
    """Proposed alternative canon. It's accepted if more people said ✅ than ❌ (the proposer can't vote)."""
    id: int
    movie_id: int
    user_id: int
    text: str
    yes: int
    no: int

    @property
    def accepted(self) -> bool:
        return self.yes > self.no


def add_canon(movie: Movie, user_id: int, text: str) -> int:
    cursor = db.conn.execute("INSERT INTO movie_canon (movie_id, guild_id, title_key, user_id, text, created_at) "
                             "VALUES (?, ?, ?, ?, ?, ?)",
                             (movie.id, movie.guild_id, title_key(movie.title), user_id, text, now().isoformat()))
    db.conn.commit()
    return cursor.lastrowid


def canon_by_message(message_id: int) -> tuple[int, int] | None:
    return db.conn.execute("SELECT id, user_id FROM movie_canon WHERE message_id = ?", (message_id,)).fetchone()


def _canon(where: str, params) -> list[Canon]:
    rows = db.conn.execute(
        f"""
        SELECT c.id, c.movie_id, c.user_id, c.text,
               (SELECT COUNT(*) FROM movie_canon_votes v WHERE v.canon_id = c.id AND v.vote = 1),
               (SELECT COUNT(*) FROM movie_canon_votes v WHERE v.canon_id = c.id AND v.vote = 0)
        FROM movie_canon c WHERE {where} ORDER BY c.id
        """, params).fetchall()
    return [Canon(*row) for row in rows]


def accepted_canon(guild_id: int, title: str, before_movie_id: int | None = None) -> list[Canon]:
    """Everything accepted as canon for a title, over every watch (across shared servers), or only watches before
    this one."""
    where, params = db.scope(guild_id)
    where, params = f"{where.replace('guild_id', 'c.guild_id')} AND c.title_key = ?", [*params, title_key(title)]
    if before_movie_id is not None:
        where, params = f"{where} AND c.movie_id < ?", [*params, before_movie_id]
    return [c for c in _canon(where, params) if c.accepted]


def canon_for_watch(movie_id: int) -> list[Canon]:
    return _canon("c.movie_id = ?", [movie_id])


def canon_list(canon: list[Canon], limit: int) -> str:
    lines = [f"• {c.text} (<@{c.user_id}>)" for c in canon[:limit]]
    if len(canon) > limit:
        lines.append(f"-# …and {len(canon) - limit} more: `/nowplaying canon`.")
    return "\n".join(lines)


def objections(movie_id: int) -> list[tuple[int, int, str | None, bool]]:
    """(user, seconds in, reason, sustained) for a watch, in film order."""
    rows = db.conn.execute("SELECT user_id, at_seconds, reason, sustained FROM movie_objections WHERE movie_id = ? "
                           "ORDER BY at_seconds, id", (movie_id,)).fetchall()
    return [(user_id, at, reason, bool(sustained)) for user_id, at, reason, sustained in rows]


# --- The committee's report ---
def morale(scores: list[int]) -> str:
    if not scores:
        return "Unknown. Nobody rated it, which says something."
    average = sum(scores) / len(scores)
    if average >= 8:
        return "High. Suspiciously high."
    if average >= 6:
        return "Adequate."
    if average >= 4:
        return "Questionable."
    return "Low. Someone should check on everyone."


def viewing_report(movie: Movie) -> discord.Embed:
    """The committee's official report on a finished watch. The same every time it's asked for."""
    scores = [s for _, s in ratings(movie.id)]
    verdicts = revealed_predictions(movie.id)
    winners = bingo_winners(movie.id)
    filed = objections(movie.id)
    canon = [c for c in canon_for_watch(movie.id) if c.accepted]
    rng = random.Random(f"report:{movie.id}")  # Its findings don't change if someone asks twice.
    watched = duration(watched_seconds(movie))
    if movie.paused_seconds >= 60:
        watched += f" (plus {duration(movie.paused_seconds)} paused)"
    lines = [f"**Film:** {movie.linked_name}" + (f" (watch #{movie.watch_number})" if (movie.watch_number or 1) > 1
                                                    else ""),
             f"**Watched:** {watched}, ended {movie.ended_at.strftime('%d %b %Y')}",
             f"**Rating:** {sum(scores) / len(scores):.1f}/10 from {plural(len(scores), 'rating')}" if scores
             else "**Rating:** none submitted",
             f"**Morale:** {morale(scores)}",
             f"**Predictions upheld:** {sum(v.called for v in verdicts)} of {len(verdicts)}" if verdicts
             else "**Predictions upheld:** nobody predicted anything",
             f"**Bingo incidents:** {len(winners)}" + (f" ({', '.join(f'<@{u}>' for u in winners)})" if winners else "")]
    sustained = sum(s for *_, s in filed)
    lines.append(f"**Objections filed:** {len(filed)}" + (f" ({sustained} sustained)" if sustained else ""))
    for user_id, at, reason, upheld in filed[:OBJECTIONS_SHOWN]:
        lines.append(f"-# `{timecode(at)}` <@{user_id}>: {reason or 'no reason given'} "
                     f"({'sustained' if upheld else 'overruled'})")
    if len(filed) > OBJECTIONS_SHOWN:
        lines.append(f"-# …and {len(filed) - OBJECTIONS_SHOWN} more.")
    lines.append(f"**New canon:** {len(canon)}")
    if canon:
        lines.append(canon_list(canon, CANON_SHOWN))
    lines += ["", f"**Committee finding:** {rng.choice(REPORT_FINDINGS)}",
              f"**Recommendation:** {rng.choice(REPORT_RECOMMENDATIONS)}"]
    embed = discord.Embed(title="📋 OFFICIAL VIEWING REPORT", description="\n".join(lines)[:4096],
                          color=discord.Color.dark_gold())
    embed.set_footer(text="Filed by the committee. No further correspondence will be entered into.")
    return embed


# --- Bingo ---
def bingo_card(movie_id: int, user_id: int) -> list[str]:
    """25 squares, numbered 1-25 left to right, top to bottom. The same for the same movie and person."""
    squares = random.Random(f"{movie_id}:{user_id}").sample(BINGO_SQUARES, BINGO_SIZE * BINGO_SIZE - 1)
    squares.insert(BINGO_FREE - 1, BINGO_FREE_SPACE)
    return squares


def bingo_marks(movie_id: int, user_id: int) -> set[int]:
    rows = db.conn.execute("SELECT square FROM movie_bingo_marks WHERE movie_id = ? AND user_id = ?",
                           (movie_id, user_id)).fetchall()
    return {BINGO_FREE} | {row[0] for row in rows}


def has_bingo(marks: set[int]) -> bool:
    return any(all(square in marks for square in line) for line in BINGO_LINES)


def bingo_winners(movie_id: int) -> list[int]:
    return [row[0] for row in db.conn.execute("SELECT user_id FROM movie_bingo_wins WHERE movie_id = ? ORDER BY rowid",
                                              (movie_id,))]


def bingo_win_count(guild_id: int, user_id: int) -> int:
    where, params = db.scope(guild_id)
    return db.conn.execute(f"SELECT COUNT(*) FROM movie_bingo_wins WHERE {where} AND user_id = ?",
                           (*params, user_id)).fetchone()[0]


def bingo_card_embed(movie: Movie, user_id: int) -> discord.Embed:
    card, marks = bingo_card(movie.id, user_id), bingo_marks(movie.id, user_id)
    rows = []
    for r in range(BINGO_SIZE):
        numbers = range(r * BINGO_SIZE + 1, (r + 1) * BINGO_SIZE + 1)
        rows.append(" ".join(" X" if n in marks else f"{n:>2}" for n in numbers))
    legend = [f"`{n:>2}` ~~{square}~~" if n in marks else f"`{n:>2}` {square}" for n, square in enumerate(card, 1)]
    embed = discord.Embed(title=f"🎯 Your bingo card: {plain_label(movie)}"[:256],
                          description="```\n" + "\n".join(rows) + "\n```\n" + "\n".join(legend),
                          color=discord.Color.green())
    embed.set_footer(text="Mark a square with /nowplaying bingo card square:<number>. Five in a row (across, down or "
                          "diagonal) wins.")
    return embed


# --- /nowplaying ---
# Everything for movie night bar /shhh lives under /nowplaying, so the rest of the slash menu stays short. Typed, it's
# !nowplaying or !np (slash commands can't have aliases, so the slash one is just /nowplaying).
@commands.hybrid_group(name="nowplaying", aliases=["np"], invoke_without_command=True,
                       description="Movie night: what's on, starting together, pauses, the watchlist, votes, bingo, ratings.")
@commands.guild_only()
async def np_group(ctx: commands.Context):
    await np_show.callback(ctx)


@np_group.command(name="show", description="What's lined up or playing, and how far in.")
async def np_show(ctx: commands.Context):
    await ctx.send(status_text(current_movie(ctx.guild.id)), allowed_mentions=NO_PINGS)


@np_group.command(name="set", description="Line up what's being watched. It doesn't start until /nowplaying start.")
@app_commands.describe(title="What we're watching")
async def np_set(ctx: commands.Context, *, title: str):
    title = one_line(title, TITLE_MAX_LENGTH)
    if not title:
        await ctx.send("What are we watching?", ephemeral=True)
        return
    movie = current_movie(ctx.guild.id)
    if movie and movie.started_at:
        await ctx.send(f"{movie.name} is still on. `/nowplaying end` it first.", ephemeral=True)
        return
    log.info("[%s] %s lined up %r", ctx.guild.name, ctx.author, title)
    await ctx.send(set_up_next(ctx.guild.id, title, ctx.author.id), allowed_mentions=NO_PINGS)


def set_up_next(guild_id: int, title: str, user_id: int) -> str:
    """Line up a title (when nothing's playing), swapping out anything already lined up. Returns the announcement."""
    movie = current_movie(guild_id)
    notes = []
    if movie and title_key(title) == title_key(movie.title):
        _update(movie.id, title=title, set_by=user_id)  # Same film, just retyped.
        movie = get_movie(movie.id)
    else:
        if movie:  # Changed our minds before starting: the old one keeps its predictions, on the watchlist.
            notes.append(archive(movie))
        movie, restored = line_up(guild_id, title, user_id)
        sealed = sealed_count(movie.id)
        if restored:
            notes.append("Back from the watchlist" + (f" with {plural(sealed, 'sealed prediction')}." if sealed else "."))
    if not notes:
        notes.append("Get your predictions in (`/nowplaying predict`) and your bingo card ready "
                     "(`/nowplaying bingo card`).")
    return "\n".join([status_text(movie), *(f"-# {note}" for note in notes)])


WATCHLIST_SHOWN = 30


@np_group.group(name="watchlist", fallback="show", invoke_without_command=True,
                description="Films to watch: added, imported from Letterboxd, or lined up and never started.")
async def np_watchlist(ctx: commands.Context):
    saved = watchlist(ctx.guild.id)
    if not saved:
        await ctx.send("🍿 The watchlist is empty. `/nowplaying watchlist add <title>` (or a Letterboxd film or list "
                       "link), or line something up and never start it.", ephemeral=True)
        return
    lines = []
    for movie in saved[:WATCHLIST_SHOWN]:
        if movie.struck_at:
            lines.append(f"~~{movie.linked_name}~~ (watched {movie.struck_at.strftime('%d %b')})")
            continue
        sealed = sealed_count(movie.id)
        line = f"**{movie.linked_name}**, added by <@{movie.set_by}>"
        lines.append(line + (f", {plural(sealed, 'sealed prediction')}" if sealed else ""))
    if len(saved) > WATCHLIST_SHOWN:
        lines.append(f"…and {len(saved) - WATCHLIST_SHOWN} more.")
    struck = sum(1 for m in saved if m.struck_at)
    embed = discord.Embed(title=f"🍿 To watch ({len(saved) - struck})", description="\n".join(lines),
                          color=discord.Color.dark_red())
    footer = "Line one up with /nowplaying set <title> (it autocompletes); any predictions come with it."
    if struck:
        footer = f"{struck} struck off as watched. " + footer
    embed.set_footer(text=footer)
    await ctx.send(embed=embed, allowed_mentions=NO_PINGS)


def to_watch_count(guild_id: int) -> int:
    return sum(1 for m in watchlist(guild_id) if not m.struck_at)


def link_onto_watchlist(guild_id: int, film: letterboxd.Film, typed_title: str) -> tuple[Movie | None, str]:
    """Give a Letterboxd film's name and link to the watchlist entry it already has, if any (one added by title
    only: "Nosferatu" becomes "Nosferatu (1922)", linked). Returns (that entry, "linked"/"already"), or (None, "")."""
    for movie in watchlist(guild_id):
        if movie.link == film.link:
            return movie, "already"
    names = {title_key(film.name), without_year(film.name)} | ({title_key(typed_title)} if typed_title else set())
    for movie in watchlist(guild_id):
        if not movie.link and title_key(movie.title) in names:
            _update(movie.id, title=film.name, title_key=title_key(film.name), link=film.link)
            return get_movie(movie.id), "linked"
    return None, ""


@np_watchlist.command(name="add",
                      description="Add a film to the watchlist (title or Letterboxd link), or a whole Letterboxd list.")
@app_commands.describe(title="The film's title",
                       link="Its Letterboxd page (letterboxd.com/film/nosferatu), or a list's, to add every film on it")
async def np_watchlist_add(ctx: commands.Context, title: str | None = None, *, link: str | None = None):
    """A film by its title, or by its Letterboxd page to get its year and link (or both). A Letterboxd **list's**
    link (`https://letterboxd.com/someone/list/halloween/`) adds every film on it, with years and links."""
    # Typed with !, it's all one string, so pick any link out of the words (either way round works).
    words = " ".join(part for part in (title, link) if part).split()
    links = [word for word in words if letterboxd.looks_like_link(word)]
    title = one_line(" ".join(word for word in words if word not in links), TITLE_MAX_LENGTH)
    if len(links) > 1:
        await ctx.send("One link at a time, please.", ephemeral=True)
        return
    if not title and not links:
        await ctx.send("Add what? Give a title, a Letterboxd link, or both.", ephemeral=True)
        return
    film = None
    if links and not title and letterboxd.is_list_link(links[0]):  # A whole list
        await import_list(ctx, links[0])
        return
    if links:
        await ctx.defer()  # Reading Letterboxd can take a moment.
        try:
            film = await letterboxd.fetch_film(links[0])
        except letterboxd.LetterboxdError as error:
            if not title and letterboxd.is_short_link(links[0]):  # A boxd.it link can be a list's too
                await import_list(ctx, links[0], film_error=error)
                return
            await ctx.send(f"🍿 {error}")
            return
        merged, how = link_onto_watchlist(ctx.guild.id, film, title)
        if how == "already":
            await ctx.send(f"🍿 {merged.linked_name} is already on the watchlist.")
            return
        if how == "linked":
            await ctx.send(f"🍿 Linked **{merged.linked_name}** on the watchlist to its Letterboxd page.")
            return
        title = film.name  # Letterboxd's name, with the year: "Nosferatu (1922)".
    movie = add_to_watchlist(ctx.guild.id, title, ctx.author.id, film.link if film else None)
    if movie is None:
        await ctx.send(f"{discord.utils.escape_markdown(title)} is already on the watchlist.", ephemeral=True)
        return
    await ctx.send(f"🍿 Added **{movie.linked_name}** to the watchlist ({to_watch_count(ctx.guild.id)} to watch).")


@np_watchlist.command(name="remove", description="Take a film off the watchlist.")
@app_commands.describe(title="The film")
async def np_watchlist_remove(ctx: commands.Context, *, title: str):
    movie = find_on_watchlist(ctx.guild.id, one_line(title, TITLE_MAX_LENGTH))
    if movie is None:
        await ctx.send(f"There's no {discord.utils.escape_markdown(one_line(title, TITLE_MAX_LENGTH))} on the "
                       "watchlist.", ephemeral=True)
        return
    _update(movie.id, dropped_at=now())  # Kept (with any predictions), just off the list.
    await ctx.send(f"🍿 Took **{movie.name}** off the watchlist.")


async def _on_watchlist(ctx: commands.Context, title: str) -> Movie | None:
    movie = find_on_watchlist(ctx.guild.id, one_line(title, TITLE_MAX_LENGTH))
    if movie is None:
        await ctx.send(f"There's no {discord.utils.escape_markdown(one_line(title, TITLE_MAX_LENGTH))} on the "
                       "watchlist.", ephemeral=True)
    return movie


@np_watchlist.command(name="strike",
                      description="Strike a film off as watched (it stays listed, crossed out), or undo it.")
@app_commands.describe(title="The film", undo="Put a struck-off film back on the watchlist properly")
async def np_watchlist_strike(ctx: commands.Context, *, title: str, undo: bool = False):  # Typed: the title is the rest
    """Strikes a film off as watched: it stays on the list, crossed out, and votes leave it out. `undo:True` puts it
    back properly. Films watched from the list are struck off by themselves when they end."""
    if undo:
        await np_watchlist_unstrike.callback(ctx, title=title)
        return
    movie = await _on_watchlist(ctx, title)
    if movie is None:
        return
    if movie.struck_at:
        await ctx.send(f"{movie.name} is already struck off.", ephemeral=True)
        return
    _update(movie.id, struck_at=now())
    await ctx.send(f"🍿 ~~{movie.name}~~ struck off as watched. It stays on the list, but votes leave it out "
                   f"(unless they `include_watched`). {to_watch_count(ctx.guild.id)} to watch.")


@np_watchlist.command(name="unstrike", description="Put a struck-off film back on the watchlist properly.",
                      with_app_command=False, extras={"merged_into": "nowplaying watchlist strike undo:True"})
@app_commands.describe(title="The film")
async def np_watchlist_unstrike(ctx: commands.Context, *, title: str):
    movie = await _on_watchlist(ctx, title)
    if movie is None:
        return
    if not movie.struck_at:
        await ctx.send(f"{movie.name} isn't struck off.", ephemeral=True)
        return
    _update(movie.id, struck_at=None)
    await ctx.send(f"🍿 **{movie.name}** is back on the watchlist. {to_watch_count(ctx.guild.id)} to watch.")


@np_watchlist.command(name="import", description="Add every film from a public Letterboxd list to the watchlist.",
                      with_app_command=False, extras={"merged_into": "nowplaying watchlist add"})
async def np_watchlist_import(ctx: commands.Context, url: str):
    await import_list(ctx, url)


async def import_list(ctx: commands.Context, url: str, film_error: letterboxd.LetterboxdError | None = None) -> None:
    """Every film on a public Letterboxd list, onto the watchlist. `film_error`: it was tried as a film's link first
    (a boxd.it link could be either), and that's the error to give if it isn't a list either."""
    await ctx.defer()  # Reading Letterboxd can take a few seconds.
    try:
        film_list = await letterboxd.fetch_list(url)
    except letterboxd.LetterboxdError as error:
        await ctx.send(f"🍿 {film_error or error}")
        return
    added = [m for m in (add_to_watchlist(ctx.guild.id, f.name, ctx.author.id, f.link) for f in film_list.films) if m]
    already = len(film_list.films) - len(added)
    log.info("[%s] %s imported %d films from %s", ctx.guild.name, ctx.author, len(added), film_list.url)
    source = f"[{discord.utils.escape_markdown(film_list.title)}](<{film_list.url}>) by {film_list.owner}"
    if not added:
        await ctx.send(f"🍿 Everything on {source} is already on the watchlist.")
        return
    names = ", ".join(m.name for m in added[:15]) + (f" and {len(added) - 15} more" if len(added) > 15 else "")
    text = f"🍿 Added **{plural(len(added), 'film')}** from {source} to the watchlist: {names}."
    if already:
        text += f"\n-# {already} {'was' if already == 1 else 'were'} already on it."
    await ctx.send(text + "\n-# `/nowplaying watchlist` to see them, `/nowplaying set <title>` to line one up.")


def _watchlist_choices(guild_id: int, current: str, struck: bool | None = None) -> list[app_commands.Choice[str]]:
    """Watchlist films matching what's typed: all of them, or only struck-off (True) or not (False) ones."""
    films = [m for m in watchlist(guild_id) if struck is None or bool(m.struck_at) == struck]
    return [app_commands.Choice(name=f"{m.title} ({'watched' if m.struck_at else 'watchlist'})"[:100],
                                value=m.title[:100])
            for m in fuzzy.starting_first(current, films, key=lambda m: m.title)]


async def watchlist_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """/nowplaying set suggests the watchlist, but any title can still be typed."""
    return _watchlist_choices(interaction.guild_id, current)


async def strike_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Films still to watch, or (undo:True) the struck-off ones."""
    return _watchlist_choices(interaction.guild_id, current, struck=bool(getattr(interaction.namespace, "undo", False)))


np_set.autocomplete("title")(watchlist_autocomplete)
np_watchlist_remove.autocomplete("title")(watchlist_autocomplete)
np_watchlist_strike.autocomplete("title")(strike_autocomplete)


# --- Voting on what's next: a native Discord poll of watchlist films. Discord counts the votes; we remember which
# answer is which film, and line up the winner when it closes (early with /nowplaying vote end, or when its time runs out).
VOTE_QUESTION = "🍿 What are we watching next?"
POLL_MAX_HOURS = 32 * 24  # Discord's longest poll. Votes default to it, so they're open until /nowplaying vote end.
POLL_ANSWER_MAX = 55  # Discord's limit for an answer's text.


@dataclass
class Vote:
    id: int
    guild_id: int
    channel_id: int
    message_id: int
    created_by: int


VOTE_COLUMNS = "id, guild_id, channel_id, message_id, created_by"


def open_vote(guild_id: int) -> Vote | None:
    row = db.conn.execute(f"SELECT {VOTE_COLUMNS} FROM movie_votes WHERE guild_id = ? AND closed_at IS NULL",
                          (guild_id,)).fetchone()
    return Vote(*row) if row else None


def open_vote_by_message(message_id: int) -> Vote | None:
    row = db.conn.execute(f"SELECT {VOTE_COLUMNS} FROM movie_votes WHERE message_id = ? AND closed_at IS NULL",
                          (message_id,)).fetchone()
    return Vote(*row) if row else None


def answer_text(title: str) -> str:
    return title if len(title) <= POLL_ANSWER_MAX else title[:POLL_ANSWER_MAX - 1] + "…"


def finish_vote(vote: Vote, poll: discord.Poll | None, user_id: int) -> str:
    """Close the vote, pick the winner and line it up if nothing's playing. Returns the announcement."""
    options = dict(db.conn.execute("SELECT answer_id, movie_id FROM movie_vote_options WHERE vote_id = ?",
                                   (vote.id,)).fetchall())
    counts = {answer.id: answer.vote_count for answer in poll.answers} if poll else {}
    best = max(counts.values(), default=0)
    if best == 0:
        db.conn.execute("UPDATE movie_votes SET closed_at = ? WHERE id = ?", (now().isoformat(), vote.id))
        db.conn.commit()
        return "🗳️ Voting's closed, but nobody voted. Still undecided."
    tied = [answer_id for answer_id, count in counts.items() if count == best and answer_id in options]
    winner = get_movie(options[random.choice(tied)])
    db.conn.execute("UPDATE movie_votes SET closed_at = ?, winner_movie_id = ? WHERE id = ?",
                    (now().isoformat(), winner.id, vote.id))
    db.conn.commit()
    log.info("Movie vote %d won by %r", vote.id, winner.title)

    text = f"🗳️ **{winner.name}** wins with {plural(best, 'vote')}"
    text += f" (a {len(tied)}-way tie, settled by coin toss)." if len(tied) > 1 else "."
    playing = current_movie(vote.guild_id)
    on_watchlist = any(m.id == winner.id for m in watchlist(vote.guild_id))
    if playing and playing.started_at:
        text += f"\n-# {playing.name} is still on: `/nowplaying set {winner.title}` when it's done."
    elif on_watchlist:
        text += "\n" + set_up_next(vote.guild_id, winner.title, user_id)
    else:
        text += "\n-# It's not on the watchlist any more, so it hasn't been lined up."
    tally = sorted(((counts.get(a, 0), get_movie(m)) for a, m in options.items()), key=lambda c: -c[0])
    return text + "\n-# " + " · ".join(f"{m.name}: {count}" for count, m in tally)


@np_group.group(name="vote", fallback="start", invoke_without_command=True,
                description="Vote on what to watch next, from the watchlist (a Discord poll).")
@app_commands.describe(count="How many random films from the watchlist (if you don't name them)",
                       hours="Optional: close it after this many hours (otherwise it's open until /nowplaying vote end)",
                       include_watched="Also pick from films struck off as watched (named films are always allowed)",
                       films="Optional: which films, separated by commas")
async def np_vote(ctx: commands.Context, count: commands.Range[int, 2, 10] = 5,
                  hours: commands.Range[int, 1, POLL_MAX_HOURS] | None = None, include_watched: bool = False, *,
                  films: str | None = None):
    if open_vote(ctx.guild.id):  # One at a time: show the one that's on
        await np_vote_show.callback(ctx)
        return
    if films:
        chosen, missing = [], []
        for name in (part.strip() for part in films.split(",")):
            if name:
                found = find_on_watchlist(ctx.guild.id, name)
                if found is None:
                    missing.append(name)
                elif found not in chosen:
                    chosen.append(found)
        if missing:
            await ctx.send(f"Not on the watchlist: {', '.join(missing)}. `/nowplaying watchlist add` them first.",
                           ephemeral=True)
            return
        if len(chosen) > 10:
            await ctx.send("Discord polls take up to 10 films.", ephemeral=True)
            return
    else:
        saved = [m for m in watchlist(ctx.guild.id) if include_watched or not m.struck_at]
        chosen = random.sample(saved, min(count, len(saved)))
    if len(chosen) < 2:
        hint = ("`/nowplaying watchlist add` some, or a Letterboxd list's link"
                if films or include_watched or len(watchlist(ctx.guild.id)) < 2
                else "the rest are struck off as watched; add `include_watched:True` to use them")
        await ctx.send(f"A vote needs at least two films: {hint}.", ephemeral=True)
        return
    poll = discord.Poll(VOTE_QUESTION, duration=timedelta(hours=hours or POLL_MAX_HOURS))
    for movie in chosen:
        poll.add_answer(text=answer_text(movie.title))
    when = f"in {plural(hours, 'hour')}, or when someone runs" if hours else "when someone runs"
    try:
        message = await ctx.send(f"-# Voting closes {when} `/nowplaying vote end`. The winner gets lined up. "
                                 f"`/nowplaying vote` finds this again.", poll=poll)
    except discord.Forbidden:
        await ctx.send("I need the **Send Polls** permission in this channel.", ephemeral=True)
        return
    cursor = db.conn.execute("INSERT INTO movie_votes (guild_id, channel_id, message_id, created_by, created_at) "
                             "VALUES (?, ?, ?, ?, ?)",
                             (ctx.guild.id, ctx.channel.id, message.id, ctx.author.id, now().isoformat()))
    db.conn.executemany("INSERT INTO movie_vote_options (vote_id, answer_id, movie_id) VALUES (?, ?, ?)",
                        [(cursor.lastrowid, n, movie.id) for n, movie in enumerate(chosen, 1)])
    db.conn.commit()
    log.info("[%s] %s started a movie vote between %d films", ctx.guild.name, ctx.author, len(chosen))


@np_vote.command(name="end", description="Close the vote now and line up the winner.")
async def np_vote_end(ctx: commands.Context):
    vote = open_vote(ctx.guild.id)
    if vote is None:
        await ctx.send("There's no vote going. `/nowplaying vote` starts one.", ephemeral=True)
        return
    channel = ctx.bot.get_channel(vote.channel_id) or ctx.channel
    try:
        message = await channel.fetch_message(vote.message_id)
        if not message.poll.is_finalised():
            message = await message.end_poll()
        poll = message.poll
    except discord.HTTPException:
        poll = None  # The poll's gone (deleted?): close the vote without a winner.
    await ctx.send(finish_vote(vote, poll, ctx.author.id), allowed_mentions=NO_PINGS)


def vote_link(vote: Vote) -> str:
    """A link that jumps straight to the vote's poll, however far up the channel it's scrolled."""
    return f"https://discord.com/channels/{vote.guild_id}/{vote.channel_id}/{vote.message_id}"


@np_vote.command(name="show", aliases=["where", "link"],
                 description="Where the vote is: a link to the poll, its films, and how long it's open.",
                 with_app_command=False, extras={"merged_into": "nowplaying vote start"})
async def np_vote_show(ctx: commands.Context):
    """Votes stay open for days and soon scroll out of sight: this posts a link that jumps straight to the poll,
    with its films, how many votes so far, and when it closes. (Discord shows each film's votes once you've voted,
    so nobody's swayed before they do.)"""
    vote = open_vote(ctx.guild.id)
    if vote is None:
        await ctx.send("There's no vote going. `/nowplaying vote` starts one.", ephemeral=True)
        return
    channel = ctx.bot.get_channel(vote.channel_id) or ctx.channel
    try:
        poll = (await channel.fetch_message(vote.message_id)).poll
    except discord.HTTPException:
        poll = None  # Can't see it (deleted?): the link's all there is
    lines = [f"🗳️ **{VOTE_QUESTION.removeprefix('🍿 ')}** [Vote here]({vote_link(vote)})"]
    if poll:
        lines.append(" · ".join(answer.text for answer in poll.answers))
        votes = sum(answer.vote_count for answer in poll.answers)
        closes = f"closes <t:{int(poll.expires_at.timestamp())}:R>, or" if poll.expires_at else "open until"
        lines.append(f"-# {plural(votes, 'vote')} so far · {closes} `/nowplaying vote end`")
    await ctx.send("\n".join(lines), allowed_mentions=NO_PINGS)


async def vote_closed_by_itself(message: discord.Message):
    """Discord posts a "poll results" message when a poll's time runs out: finish that vote."""
    if message.type != discord.MessageType.poll_result or message.reference is None:
        return
    vote = open_vote_by_message(message.reference.message_id)
    if vote is None:
        return  # Not ours, or already closed with /nowplaying vote end.
    try:
        poll = (await message.channel.fetch_message(vote.message_id)).poll
    except discord.HTTPException:
        poll = None
    await message.channel.send(finish_vote(vote, poll, vote.created_by), allowed_mentions=NO_PINGS)


async def start_movie(ctx: commands.Context, movie: Movie) -> str:
    """Start it now, and return the announcement."""
    _update(movie.id, started_at=now(), watch_number=next_watch_number(ctx.guild.id, movie.title))
    movie = get_movie(movie.id)
    log.info("[%s] %s started %r", ctx.guild.name, ctx.author, movie.title)
    await set_bot_status(ctx.bot, movie.title)
    text = (f"🎬 **Starting: {movie.label}.** Phones down, lights off.\n"
            f"-# {film_clock(movie)}. `/nowplaying pause` if you need to, `/shhh` if people won't be quiet.")
    canon = accepted_canon(movie.guild_id, movie.title, before_movie_id=movie.id)
    if canon:  # Watched before: remind everyone what's been established.
        text += f"\n📜 **Established canon:**\n{canon_list(canon, CANON_SHOWN)}"
    return text


@np_group.command(name="start", aliases=["countdown", "go"],
                  description="Start the film (or carry on after a pause): everyone press play on GO.")
async def np_start(ctx: commands.Context):
    """Starts what's lined up, now: a big **GO** for everyone to press play on. Paused? It carries on, the same way.
    (Already playing without the bot? `/nowplaying sync` with the time starts it at the right spot instead.)"""
    movie = current_movie(ctx.guild.id)
    if movie is None:
        await ctx.send("Nothing's lined up. `/nowplaying set <title>` first.", ephemeral=True)
    elif movie.started_at and movie.paused_at:
        await resume_movie(ctx, movie)
    elif movie.started_at:
        await ctx.send(f"{movie.name} has already started.", ephemeral=True)
    else:
        await ctx.send("# ▶️ GO!\n" + await start_movie(ctx, movie), allowed_mentions=NO_PINGS)


async def _edit(message: discord.Message, content: str) -> None:
    try:
        await message.edit(content=content)
    except discord.HTTPException:
        pass  # The message is gone or uneditable: nothing to swap


async def _playing(ctx: commands.Context) -> Movie | None:
    movie = current_movie(ctx.guild.id)
    if movie is None or movie.started_at is None:
        await ctx.send("Nothing's playing. " + ("`/nowplaying start` it first." if movie else "`/nowplaying set <title>` first."),
                       ephemeral=True)
        return None
    return movie


@np_group.command(name="pause", description="Pause the film (snacks, toilet, an argument).")
@app_commands.describe(reason="Optional: what for")
async def np_pause(ctx: commands.Context, *, reason: str | None = None):
    movie = await _playing(ctx)
    if movie is None:
        return
    if movie.paused_at:
        await ctx.send("It's already paused. `/nowplaying start` to carry on.", ephemeral=True)
        return
    _update(movie.id, paused_at=now())
    movie = current_movie(ctx.guild.id)
    reason = one_line(reason)
    text = f"⏸️ **Paused** {movie.name} at {timecode(watched_seconds(movie))}."
    if reason:
        text += f"\n> {reason}"
    await ctx.send(f"{text}\n-# Paused {live(movie.paused_at)}. `/nowplaying start` to carry on.", allowed_mentions=NO_PINGS)
    await set_bot_status(ctx.bot, f"{movie.title} (paused)")


@np_group.command(name="sync", aliases=["catchup"],
                  description="Back in sync: where the film is and when to press play. Or correct the bot's clock.")
@app_commands.describe(
    position="Only if the bot's clock is wrong: where the film really is (1:07:30, 47m). Empty: catch up")
async def np_sync(ctx: commands.Context, *, position: str | None = None):
    """Fallen out of sync? On its own, it tells just you exactly where the film is, and a moment to skip to and
    press play so you're back in step. Give a time (`/nowplaying sync 1:07:30`) if the bot's clock is wrong (the
    film was restarted, or started without the bot): it sets where the film really is, and starts it if it hadn't
    been. Typed, `!np sct 1:07:30` and `!np elapsed` work too."""
    if position and position.strip():
        await np_sct.callback(ctx, position=position)
    else:
        await np_elapsed.callback(ctx)


@np_group.command(name="sct", aliases=["seek"], usage="<time>",
                  description="Set current time: correct where the film is (e.g. 1:07:30), if the bot's clock is off.",
                  with_app_command=False, extras={"merged_into": "nowplaying sync"})
async def np_sct(ctx: commands.Context, *, position: str):
    seconds = parse_timecode(position)
    if seconds is None:
        await ctx.send(f"I don't understand `{one_line(position, 50)}` as a time in the film. Try {TIMECODE_EXAMPLES}.",
                       ephemeral=True)
        return
    movie = current_movie(ctx.guild.id)
    if movie is None:
        await ctx.send("Nothing's lined up. `/nowplaying set <title>` first.", ephemeral=True)
        return
    note = ""
    if movie.started_at is None:  # Started without the bot: start it now, already that far in.
        await start_movie(ctx, movie)
        movie = get_movie(movie.id)
        note = " It's started too."
    # Move the start so the film is exactly that far in, now (or as of the pause). Pauses so far still count as
    # pauses, so the time-paused total at the end stays right.
    reference = movie.paused_at or now()
    _update(movie.id, started_at=reference - timedelta(seconds=seconds + movie.paused_seconds))
    movie = get_movie(movie.id)
    log.info("[%s] %s set %r to %s", ctx.guild.name, ctx.author, movie.title, timecode(seconds))
    text = f"⏱️ **{movie.label}** is now at **{timecode(seconds)}**.{note}"
    if movie.paused_at:
        text += "\n-# Still paused. `/nowplaying start` to carry on."
    else:
        text += f"\n-# {film_clock(movie)}. Out of sync? `/nowplaying sync` to catch up."
    await ctx.send(text)


@np_group.command(name="elapsed", description="Exactly how far into the film we are, to get back in sync.",
                  with_app_command=False, extras={"merged_into": "nowplaying sync"})
async def np_elapsed(ctx: commands.Context):
    movie = await _playing(ctx)
    if movie is None:
        return
    if movie.paused_at:
        text = (f"⏸️ **{movie.label}** is paused at **{timecode(watched_seconds(movie))}**.\n"
                "-# Skip there, and press play when someone runs `/nowplaying start`.")
    else:
        # A moment a few seconds ahead, on a whole second (Discord timestamps are whole seconds): skip to where the
        # film will be then, and press play when the timestamp says so.
        at = now()
        sync_at = math.ceil(at.timestamp()) + SYNC_LEAD_SECONDS
        position = watched_seconds(movie) + round(sync_at - at.timestamp())
        text = (f"⏱️ **{movie.label}** is at **{timecode(watched_seconds(movie))}** (as of <t:{int(at.timestamp())}:T>).\n"
                f"To catch up: skip to **{timecode(position)}**, pause, and press play <t:{sync_at}:R>.")
        message = await ctx.send(text, ephemeral=True)  # Only the person catching up needs it.
        # Once it's time, swap the countdown out, so it doesn't sit there saying "press play 8 seconds ago".
        await asyncio.sleep(max(sync_at - now().timestamp(), 0))
        await _edit(message, f"▶️ **{movie.label}**: you should be at **{timecode(position)}** and back in sync.")
        return
    await ctx.send(text, ephemeral=True)


@np_group.command(name="resume", description="Carry on after a pause.", with_app_command=False,
                  extras={"merged_into": "nowplaying start"})
async def np_resume(ctx: commands.Context):
    movie = await _playing(ctx)
    if movie is None:
        return
    if not movie.paused_at:
        await ctx.send("It's not paused.", ephemeral=True)
        return
    await resume_movie(ctx, movie)


async def resume_movie(ctx: commands.Context, movie: Movie) -> None:
    """Carry on after a pause: a big GO, like the start, so everyone presses play together."""
    paused_for = int((now() - movie.paused_at).total_seconds())
    _update(movie.id, paused_at=None, paused_seconds=movie.paused_seconds + paused_for)
    movie = get_movie(movie.id)
    text = f"# ▶️ GO!\n**Resumed** {movie.name} at {timecode(watched_seconds(movie))}, after {duration(paused_for)}."
    if paused_for > LONG_PAUSE_SECONDS:
        text += f"\n-# {random.choice(LONG_PAUSE_LINES)}"
    await ctx.send(f"{text}\n-# {film_clock(movie)}.", allowed_mentions=NO_PINGS)
    await set_bot_status(ctx.bot, movie.title)


@np_group.command(name="end", description="The film's over: reveal the predictions and get the ratings in.")
async def np_end(ctx: commands.Context):
    movie = current_movie(ctx.guild.id)
    if movie is None:
        await ctx.send("Nothing's on.", ephemeral=True)
        return
    if movie.started_at is None:
        await ctx.send(f"🍿 It never started. {archive(movie)}", allowed_mentions=NO_PINGS)
        return
    ended = now()
    if movie.paused_at:
        movie.paused_seconds += int((ended - movie.paused_at).total_seconds())
    _update(movie.id, ended_at=ended, paused_at=None, paused_seconds=movie.paused_seconds)
    movie = get_movie(movie.id)
    log.info("[%s] %s ended %r", ctx.guild.name, ctx.author, movie.title)
    text = f"🎬 **That's {movie.label} done.** {duration(watched_seconds(movie))} watched"
    text += f", plus {duration(movie.paused_seconds)} paused." if movie.paused_seconds >= 60 else "."
    winners = bingo_winners(movie.id)
    if winners:
        text += "\n🎉 Bingo: " + ", ".join(f"<@{u}>" for u in winners)
    text += ("\n⭐ Rate it with `/nowplaying rate <1-10>`, then `/nowplaying history` with the film for the official "
             "report.")
    if movie.from_watchlist:
        keep_on_watchlist_struck(movie)
        text += "\n-# Struck off the watchlist."
    await ctx.send(text, allowed_mentions=NO_PINGS)
    await reveal_predictions(ctx.channel, movie)
    await set_bot_status(ctx.bot, None)


@np_group.command(name="history",
                  description="What we've watched and how it rated, or one film's report and predictions.")
@app_commands.describe(film="One film: the committee's report on it and what was predicted (empty: everything watched)")
async def np_history(ctx: commands.Context, *, film: str | None = None):
    """On its own: what's been watched, with its ratings and how many predictions were called. Name a film (it
    autocompletes, newest first) for the committee's official viewing report on it and what everyone predicted.
    Watched it more than once? `Alien #1` is the first time. Typed, `!np committeesviews` (the last film's report)
    and `!np predictions` work too."""
    if film and film.strip():
        movie = find_watched(ctx.guild.id, film)
        if movie is None:
            await ctx.send(f"No finished film called “{one_line(film, TITLE_MAX_LENGTH)}”. Try `/nowplaying history`.",
                           ephemeral=True)
            return
        await ctx.send(embeds=[viewing_report(movie), predictions_embed(movie)], allowed_mentions=NO_PINGS)
        return
    movies = watched_movies(ctx.guild.id, HISTORY_SHOWN)
    if not movies:
        await ctx.send("🎬 Nothing watched yet.", ephemeral=True)
        return
    lines = []
    for movie in movies:
        scores = [s for _, s in ratings(movie.id)]
        line = f"**{movie.label}**: " + (f"{sum(scores) / len(scores):.1f}/10 ({plural(len(scores), 'rating')})"
                                        if scores else "not rated")
        verdicts = revealed_predictions(movie.id)
        if verdicts:
            line += f", {sum(v.called for v in verdicts)}/{len(verdicts)} predictions called"
        lines.append(f"{line}, {movie.ended_at.strftime('%d %b %Y')}")
    embed = discord.Embed(title="🎬 What we've watched", description="\n".join(lines), color=discord.Color.dark_red())
    embed.set_footer(text="One film's report and predictions: /nowplaying history <film> (add #2 for a second watch).")
    await ctx.send(embed=embed)


def verdict_line(verdict: Verdict) -> str:
    mark = "✅" if verdict.called else "❌" if verdict.no > verdict.yes else "⚖️"
    return f"{mark} <@{verdict.user_id}>: {verdict.text} ({verdict.yes}–{verdict.no})"


@np_group.command(name="predictions", description="What was predicted for a film we've watched, and who called it.",
                  with_app_command=False, extras={"merged_into": "nowplaying history"})
async def np_predictions(ctx: commands.Context, *, title: str | None = None):
    movie = find_watched(ctx.guild.id, title)
    if movie is None:
        await ctx.send(f"No finished film called “{one_line(title, TITLE_MAX_LENGTH)}”. Try `/nowplaying history`."
                       if title else "🎬 Nothing watched yet.", ephemeral=True)
        return
    await ctx.send(embed=predictions_embed(movie), allowed_mentions=NO_PINGS)


def predictions_embed(movie: Movie) -> discord.Embed:
    """What was predicted for a film that's been watched, and who called it."""
    verdicts = revealed_predictions(movie.id)
    lines, length = [], 0
    for verdict in verdicts:
        line = verdict_line(verdict)
        if length + len(line) > 3800:  # Embed descriptions stop at 4096.
            lines.append(f"…and {len(verdicts) - len(lines)} more.")
            break
        lines.append(line)
        length += len(line) + 1
    embed = discord.Embed(title=f"🔮 Predictions for {plain_label(movie)}, {movie.ended_at.strftime('%d %b %Y')}"[:256],
                          description="\n".join(lines) or "Nobody predicted anything.", color=discord.Color.purple())
    if verdicts:
        embed.set_footer(text=f"{sum(v.called for v in verdicts)} of {len(verdicts)} called. ✅ called it, "
                              "❌ didn't, ⚖️ undecided (votes ✅–❌).")
    return embed


async def watched_title_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    films = fuzzy.starting_first(current, watched_movies(interaction.guild_id), key=lambda m: m.title)
    return [app_commands.Choice(name=f"{m.title} (watch #{m.watch_number or 1}, {m.ended_at.strftime('%d %b %Y')})"[:100],
                                value=f"id:{m.id}") for m in films]


np_history.autocomplete("film")(watched_title_autocomplete)


@np_group.command(name="committeesviews", description="The committee's official report on a film we've watched.",
                  with_app_command=False, extras={"merged_into": "nowplaying history"})
async def np_committeesviews(ctx: commands.Context, *, title: str | None = None):
    movie = find_watched(ctx.guild.id, title)
    if movie is None:
        await ctx.send(f"No finished film called “{one_line(title, TITLE_MAX_LENGTH)}”. Try `/nowplaying history`."
                       if title else "🎬 Nothing watched yet. The committee has nothing to report.", ephemeral=True)
        return
    await ctx.send(embed=viewing_report(movie), allowed_mentions=NO_PINGS)



@np_group.command(name="canon", description="Propose alternative canon for the film, for a vote. Empty: what's canon.")
@app_commands.describe(claim="What's now true about this film, e.g. Jones the cat works for Weyland-Yutani")
async def np_canon(ctx: commands.Context, *, claim: str | None = None):
    claim = one_line(claim)
    if not claim:
        movie = current_movie(ctx.guild.id) or movie_to_rate(ctx.guild.id)
        if movie is None:
            await ctx.send("No film to have canon for. `/nowplaying set <title>` first.", ephemeral=True)
            return
        canon = accepted_canon(ctx.guild.id, movie.title)
        if not canon:
            await ctx.send(f"📜 Nothing's canon for {movie.name} yet. `/nowplaying canon <claim>` to change that.",
                           allowed_mentions=NO_PINGS)
            return
        await ctx.send(f"📜 **Canon for {movie.name}:**\n{canon_list(canon, 20)}", allowed_mentions=NO_PINGS)
        return
    movie = current_movie(ctx.guild.id)
    if movie is None:
        await ctx.send("Nothing's on to rewrite. `/nowplaying set <title>` first.", ephemeral=True)
        return
    canon_id = add_canon(movie, ctx.author.id, claim)
    message = await ctx.send(f"📜 {ctx.author.mention} proposes, as canon for **{movie.label}**:\n> {claim}\n"
                             f"-# React {CALLED_IT} to accept it, {NOT_IT} to reject it (not on your own). Accepted "
                             "canon comes back every time it's watched.", allowed_mentions=NO_PINGS)
    if message is not None:
        db.conn.execute("UPDATE movie_canon SET message_id = ? WHERE id = ?", (message.id, canon_id))
        db.conn.commit()
        try:
            await message.add_reaction(CALLED_IT)
            await message.add_reaction(NOT_IT)
        except discord.HTTPException:
            pass  # No Add Reactions permission: people can still add them.


@np_group.command(name="objection", description="Formally object to something in the film. The committee will rule.")
@app_commands.describe(reason="Optional: what you object to")
async def np_objection(ctx: commands.Context, *, reason: str | None = None):
    movie = await _playing(ctx)
    if movie is None:
        return
    at = watched_seconds(movie)
    reason = one_line(reason) or None
    sustained = random.randrange(SUSTAINED_ONE_IN) == 0
    db.conn.execute("INSERT INTO movie_objections (movie_id, guild_id, user_id, at_seconds, reason, sustained, "
                    "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (movie.id, movie.guild_id, ctx.author.id, at, reason, int(sustained), now().isoformat()))
    db.conn.commit()
    text = f"⚖️ **OBJECTION FILED — {timecode(at)}**"
    if reason:
        text += f"\n> {reason}"
    text += f"\n{random.choice(SUSTAINED_LINES if sustained else OVERRULED_LINES)}\n-# Filed by {ctx.author.mention}."
    await ctx.send(text, allowed_mentions=NO_PINGS)


# --- /shhh, /nowplaying rate, /nowplaying predict ---
@commands.hybrid_command(name="shhh", description="Tell everyone to be quiet for this bit.")
@commands.guild_only()
@app_commands.describe(reason="Optional: why this bit matters")
async def shhh(ctx: commands.Context, *, reason: str | None = None):
    """A big 🤫 SHHHH for everyone, naming the film if one's on (`/nowplaying`), with your reason if you give one. Pings
    nobody."""
    movie = current_movie(ctx.guild.id)
    if movie and movie.started_at:
        line = random.choice(SHHH_DURING_LINES).format(title=movie.name)
    else:
        line = random.choice(SHHH_LINES)
    text = f"# 🤫 SHHHH\n{line}"
    reason = one_line(reason)  # One line, so it all stays in the quote.
    if reason:
        text += f"\n> {reason}"
    # Nobody is pinged: a notification is the opposite of quiet.
    await ctx.send(f"{text}\n-# Requested by {ctx.author.mention}.", allowed_mentions=NO_PINGS)


@np_group.command(name="rate", description="Rate the film out of 10, or see everyone's ratings.")
@app_commands.describe(score="1 to 10 (leave empty to see the ratings)")
async def rate(ctx: commands.Context, score: commands.Range[int, 1, 10] | None = None):
    movie = movie_to_rate(ctx.guild.id)
    if movie is None:
        await ctx.send("Nothing to rate yet. Watch something first.", ephemeral=True)
        return
    if score is None:
        scores = ratings(movie.id)
        lines = [f"<@{user_id}>: {s}/10" for user_id, s in scores]
        await ctx.send("\n".join([f"⭐ **{movie.label}**: {rating_summary(movie.id)}", *lines]),
                       allowed_mentions=NO_PINGS)
        return
    db.conn.execute("INSERT INTO movie_ratings (movie_id, user_id, score) VALUES (?, ?, ?)"
                    " ON CONFLICT (movie_id, user_id) DO UPDATE SET score = excluded.score",
                    (movie.id, ctx.author.id, score))
    db.conn.commit()
    await ctx.send(f"⭐ {ctx.author.mention} gave **{movie.label}** a {score}/10.\n{rating_summary(movie.id)}",
                   allowed_mentions=NO_PINGS)


@np_group.command(name="predict", description="Make a sealed prediction about the film. Revealed at the end.")
@app_commands.describe(guess="What you think will happen")
async def predict(ctx: commands.Context, *, guess: str):
    movie = current_movie(ctx.guild.id)
    guess = one_line(guess)
    if movie is None:
        await ctx.send("Nothing's lined up to predict. `/nowplaying set <title>` first.", ephemeral=True)
        return
    if not guess:
        await ctx.send("Predict what?", ephemeral=True)
        return
    add_prediction(movie, ctx.author.id, guess)
    announcement = f"🔮 {ctx.author.mention} has made a sealed prediction about {movie.label}."
    if ctx.interaction:
        await ctx.send(announcement, allowed_mentions=NO_PINGS)
        await ctx.send(f"🔮 Sealed: {guess}\n-# Revealed when someone runs `/nowplaying end`.", ephemeral=True,
                       allowed_mentions=NO_PINGS)
        return
    try:
        await ctx.message.delete()  # Typed with !, so hide it until the reveal.
    except discord.HTTPException:
        announcement += "\n-# I couldn't hide your message (I need Manage Messages). Use `/nowplaying predict` to keep it secret."
    await ctx.send(announcement, allowed_mentions=NO_PINGS)


# --- /nowplaying bingo ---
async def _bingo_movie(ctx: commands.Context, need_started: bool) -> Movie | None:
    movie = current_movie(ctx.guild.id)
    if movie is None:
        await ctx.send("No film lined up. `/nowplaying set <title>` first.", ephemeral=True)
    elif need_started and movie.started_at is None:
        await ctx.send("No marking before it starts. Wait for `/nowplaying start`.", ephemeral=True)
    else:
        return movie
    return None


@np_group.group(name="bingo", fallback="card", invoke_without_command=True,
                description="Your bingo card (just for you), or mark a square off it.")
@app_commands.describe(square="Mark this square off (its number, or its words). Empty: just your card",
                       unmark="Unmark the square instead, if you marked it by mistake")
async def bingo_group(ctx: commands.Context, square: commands.Range[int, 1, 25] | None = None, unmark: bool = False):
    """Movie bingo: everyone gets their own 5×5 card of film tropes for each film. On its own, it's your card (only
    you see it). Give a square (`/nowplaying bingo card square:7`; it autocompletes with the squares' words) to mark
    it off as it happens: five in a row is a BINGO, announced to everyone, and goes on your rap sheet. Marked one by
    mistake? Add `unmark:True`. Your card follows, so you can see where you stand. Typed, `!np bingo mark 7`,
    `!np bingo unmark 7` and `!np bingo card` work too."""
    if square is None:
        await bingo_show.callback(ctx)
        return
    changed = await (bingo_unmark if unmark else bingo_mark).callback(ctx, square)
    if changed and ctx.interaction:  # Typed, the card would go by DM: not after every mark
        await ctx.send(embed=bingo_card_embed(current_movie(ctx.guild.id), ctx.author.id), ephemeral=True)


@bingo_group.command(name="card", description="See your bingo card for this film (only you can see it).",
                     with_app_command=False, extras={"merged_into": "nowplaying bingo card"})
async def bingo_show(ctx: commands.Context):
    movie = await _bingo_movie(ctx, need_started=False)
    if movie is None:
        return
    embed = bingo_card_embed(movie, ctx.author.id)
    if ctx.interaction:
        await ctx.send(embed=embed, ephemeral=True)
        return
    try:  # Typed with !, which can't be private, so it goes by DM.
        await ctx.author.send(embed=embed)
        await ctx.send("🎯 Sent you your card.")
    except discord.HTTPException:
        await ctx.send("I couldn't DM you. Use `/nowplaying bingo card` instead.")


@bingo_group.command(name="mark", description="Mark off a square on your card.", with_app_command=False,
                     extras={"merged_into": "nowplaying bingo card"})
async def bingo_mark(ctx: commands.Context, square: commands.Range[int, 1, 25]) -> bool:
    """Whether it was marked."""
    movie = await _bingo_movie(ctx, need_started=True)
    if movie is None:
        return False
    marks = bingo_marks(movie.id, ctx.author.id)
    if square in marks:
        await ctx.send("That one's already marked." if square != BINGO_FREE else "That's the free space.", ephemeral=True)
        return False
    db.conn.execute("INSERT INTO movie_bingo_marks (movie_id, user_id, square) VALUES (?, ?, ?)",
                    (movie.id, ctx.author.id, square))
    marks.add(square)
    text = f"🎯 {ctx.author.mention} marked **{bingo_card(movie.id, ctx.author.id)[square - 1]}** ({len(marks)}/25)"
    if has_bingo(marks) and ctx.author.id not in bingo_winners(movie.id):
        db.conn.execute("INSERT INTO movie_bingo_wins (movie_id, guild_id, user_id) VALUES (?, ?, ?)",
                        (movie.id, movie.guild_id, ctx.author.id))
        text += f"\n# 🎉 BINGO!\n{ctx.author.mention} got five in a row."
    db.conn.commit()
    await ctx.send(text, allowed_mentions=NO_PINGS)
    return True


@bingo_group.command(name="unmark", description="Unmark a square you marked by mistake.", with_app_command=False,
                     extras={"merged_into": "nowplaying bingo card unmark:True"})
async def bingo_unmark(ctx: commands.Context, square: commands.Range[int, 1, 25]) -> bool:
    """Whether it was unmarked."""
    movie = await _bingo_movie(ctx, need_started=False)
    if movie is None:
        return False
    if square == BINGO_FREE or square not in bingo_marks(movie.id, ctx.author.id):
        await ctx.send("That square isn't marked (or it's the free space).", ephemeral=True)
        return False
    db.conn.execute("DELETE FROM movie_bingo_marks WHERE movie_id = ? AND user_id = ? AND square = ?",
                    (movie.id, ctx.author.id, square))
    db.conn.commit()
    await ctx.send(f"Unmarked square {square}. A bingo already called stays called.", ephemeral=True)
    return True


async def bingo_square_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
    movie = current_movie(interaction.guild_id)
    if movie is None:
        return []
    card, marks = bingo_card(movie.id, interaction.user.id), bingo_marks(movie.id, interaction.user.id)
    unmarking = bool(getattr(interaction.namespace, "unmark", False))  # Then it's the marked ones (not the free space)
    unmarked = [(n, square) for n, square in enumerate(card, 1)
                if (n in marks and n != BINGO_FREE if unmarking else n not in marks)]
    typed = current.strip()
    # A number picks that square; anything else is looked for in the squares' wording.
    found = [(n, s) for n, s in unmarked if str(n) == typed] if typed.isdigit() else \
        fuzzy.starting_first(typed, unmarked, key=lambda pair: pair[1])
    return [app_commands.Choice(name=f"{n}. {square}"[:100], value=n) for n, square in found]


bingo_group.autocomplete("square")(bingo_square_autocomplete)


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    if (command.root_parent or command).name != "nowplaying":
        return "", []
    text = ("1. `/nowplaying set <title>` lines it up. Nothing starts yet, so people can `/nowplaying predict` and look at "
            "their `/nowplaying bingo card`.\n"
            "2. `/nowplaying start` starts it now, with a big GO for everyone to press play on (the bot's status shows "
            "what's on). `/nowplaying pause [reason]` for a break, which doesn't count towards the time watched, and "
            "`/nowplaying start` again to carry on, with another GO. `/shhh` when people won't be quiet. Fallen out of "
            "sync? `/nowplaying sync` gives just you the exact spot and when to press play to catch up. Bot's clock "
            "wrong (restarted the film, started it without the bot)? `/nowplaying sync 1:07:30` sets where it really "
            "is.\n"
            "3. `/nowplaying bingo card square:<number>` as things happen (add `unmark:True` to take one back). Five "
            "in a row wins. `/nowplaying objection [reason]` formally objects (timestamped; the committee rules). "
            f"`/nowplaying canon <claim>` proposes alternative canon: {CALLED_IT}/{NOT_IT} to vote, and accepted canon "
            "is read out whenever it's watched again.\n"
            f"4. `/nowplaying end` reveals the predictions: react {CALLED_IT} if they called it, {NOT_IT} if not "
            "(not on your own). Then everyone `/nowplaying rate`s it, and `/nowplaying history <film>` gets the "
            "committee's official report, with what was predicted and who called it.\n"
            "• Anyone can run any of it. Called predictions and bingo wins go on the rap sheet; `/nowplaying history` "
            "on its own lists what you've watched with its ratings.\n"
            "• `/nowplaying watchlist` is what's still to watch: `add` a film (by title, or by Letterboxd link to get "
            "its year and link) or a whole public Letterboxd list (its link), `remove` one, or `strike` one off as "
            "watched (it stays listed, crossed out, and votes skip it; `undo:True` puts it back). Films watched from "
            "the list are struck off when they end. Films swapped out with `/nowplaying set` or ended before they "
            "started go on it too, with their predictions. `/nowplaying set` autocompletes from it; `Alien` finds "
            "`Alien (1979)`.\n"
            "• Can't decide? `/nowplaying vote` posts a poll of 5 random films from the watchlist (or name them: "
            "`films:Alien, Deadstream`). It's open until `/nowplaying vote end` (or `hours:` for a timed one); then the "
            "winner's lined up. Lost it up the channel? `/nowplaying vote` again links to it.\n"
            "• Watching something again is a new watch (Alien (watch #2)), with fresh predictions, bingo cards and "
            "ratings. `/nowplaying history Alien #1` looks up an earlier one.\n"
            "• Typed with `!np`, the old names still work: `resume`, `elapsed`, `sct`, `watchlist import`, `unstrike`, "
            "`vote show`, `predictions`, `committeesviews` and `bingo mark`/`unmark`.")
    return "", [("🎬 How movie night works", text, False)]


async def setup(bot: commands.Bot):
    for command in (np_group, shhh):  # rate, predict and bingo are under np_group
        bot.add_command(command)
    bot.add_listener(prediction_vote, "on_raw_reaction_add")
    bot.add_listener(prediction_unvote, "on_raw_reaction_remove")
    bot.add_listener(vote_closed_by_itself, "on_message")
