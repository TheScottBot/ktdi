"""Movie night: /np (set, start, pause, resume, end, history), /shhh, /rate, /predict and /bingo.

A server has at most one current movie: its newest row in `movies` with no ended_at. It's lined up with /np set,
and nothing starts until /np start. Ending it reveals the predictions (people react ✅/❌ to judge them) and asks
for ratings. Bingo cards aren't stored: each is shuffled from a seed of (movie, person), so it's the same every time.
"""

import asyncio
import math
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from ktdi import common, db
from ktdi.common import NO_PINGS, log, plural
from ktdi.lib import letterboxd

HELP_CATEGORY = "🎬 Movie night"
TITLE_MAX_LENGTH = 100
TEXT_MAX_LENGTH = 200
HISTORY_SHOWN = 10
LONG_PAUSE_SECONDS = 5 * 60
COUNTDOWN_FROM = 5
SYNC_LEAD_SECONDS = 10  # /np elapsed: time to skip to the spot before pressing play.
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
    watch_number: int | None  # 1 for the first time we watched this title, 2 for the second...; set by /np start.
    link: str | None  # Its Letterboxd page, if it was imported from a list.
    dropped_at: datetime | None  # Taken off the watchlist.

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
                 "archived_at, watch_number, link, dropped_at")
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
     dropped) = row
    return Movie(id_, guild_id, title, set_by, _time(created), _time(started), _time(paused), paused_seconds,
                 _time(ended), _time(archived), watch_number, link, _time(dropped))


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
    keeps its own order. Per server, like the current film."""
    rows = db.conn.execute(f"SELECT {MOVIE_COLUMNS} FROM movies WHERE guild_id = ? AND archived_at IS NOT NULL "
                           "AND dropped_at IS NULL ORDER BY archived_at DESC, id", (guild_id,)).fetchall()
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


def sealed_count(movie_id: int) -> int:
    return db.conn.execute("SELECT COUNT(*) FROM movie_predictions WHERE movie_id = ?", (movie_id,)).fetchone()[0]


def archive(movie: Movie) -> str:
    """Put a film that never started on the watchlist, keeping its predictions. Returns a note saying so."""
    _update(movie.id, archived_at=now())
    sealed = sealed_count(movie.id)
    kept = f" with its {plural(sealed, 'sealed prediction')}" if sealed else ""
    return f"{movie.name} is on the watchlist (not yet watched){kept}. `/np set {movie.title}` brings it back."


def line_up(guild_id: int, title: str, user_id: int) -> tuple[Movie, bool]:
    """Line up a title: back from the watchlist (predictions and all) if it's there, otherwise new.
    Returns the film and whether it came off the watchlist."""
    saved = find_on_watchlist(guild_id, title)
    if saved:
        if title_key(saved.title) != title_key(title):
            title = saved.title  # Found without the year: keep the fuller "Alien (1979)".
        _update(saved.id, archived_at=None, title=title, title_key=title_key(title), set_by=user_id)
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
        return "🎬 Nothing's lined up. Pick something with `/np set <title>`."
    if movie.started_at is None:
        label = f"[{movie.label}](<{movie.link}>)" if movie.link else movie.label
        return f"🎬 **Up next:** {label}\n-# Lined up by <@{movie.set_by}>. `/np start` when everyone's ready."
    if movie.paused_at:
        return (f"⏸️ **Paused:** {movie.label} at {timecode(watched_seconds(movie))}\n"
                f"-# Paused {live(movie.paused_at)}. `/np resume` to carry on.")
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
    """Only revealed ones: a film's predictions stay sealed until its /np end."""
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


def _vote(payload: discord.RawReactionActionEvent) -> tuple[int, int] | None:
    """(prediction id, vote) if this reaction is someone judging a prediction."""
    emoji = str(payload.emoji)
    if emoji not in (CALLED_IT, NOT_IT) or payload.user_id == common.bot.user.id:
        return None
    found = prediction_by_message(payload.message_id)
    if found is None or found[1] == payload.user_id:  # Nobody judges their own.
        return None
    return found[0], int(emoji == CALLED_IT)


async def prediction_vote(payload: discord.RawReactionActionEvent):
    if vote := _vote(payload):
        db.conn.execute("INSERT OR IGNORE INTO movie_prediction_votes (prediction_id, user_id, vote) VALUES (?, ?, ?)",
                        (vote[0], payload.user_id, vote[1]))
        db.conn.commit()


async def prediction_unvote(payload: discord.RawReactionActionEvent):
    if vote := _vote(payload):
        db.conn.execute("DELETE FROM movie_prediction_votes WHERE prediction_id = ? AND user_id = ? AND vote = ?",
                        (vote[0], payload.user_id, vote[1]))
        db.conn.commit()


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
    embed.set_footer(text="Mark a square with /bingo mark <number>. Five in a row (across, down or diagonal) wins.")
    return embed


# --- /np ---
@commands.hybrid_group(name="np", description="Movie night: what's playing. Set it, start it, pause it, end it.",
                       invoke_without_command=True)
@commands.guild_only()
async def np_group(ctx: commands.Context):
    await np_show.callback(ctx)


@np_group.command(name="show", description="What's lined up or playing, and how far in.")
async def np_show(ctx: commands.Context):
    await ctx.send(status_text(current_movie(ctx.guild.id)), allowed_mentions=NO_PINGS)


@np_group.command(name="set", description="Line up what's being watched. It doesn't start until /np start.")
@app_commands.describe(title="What we're watching")
async def np_set(ctx: commands.Context, *, title: str):
    title = one_line(title, TITLE_MAX_LENGTH)
    if not title:
        await ctx.send("What are we watching?", ephemeral=True)
        return
    movie = current_movie(ctx.guild.id)
    if movie and movie.started_at:
        await ctx.send(f"{movie.name} is still on. `/np end` it first.", ephemeral=True)
        return
    notes = []
    if movie and title_key(title) == title_key(movie.title):
        _update(movie.id, title=title, set_by=ctx.author.id)  # Same film, just retyped.
        movie = get_movie(movie.id)
    else:
        if movie:  # Changed our minds before starting: the old one keeps its predictions, on the watchlist.
            notes.append(archive(movie))
        movie, restored = line_up(ctx.guild.id, title, ctx.author.id)
        sealed = sealed_count(movie.id)
        if restored:
            notes.append("Back from the watchlist" + (f" with {plural(sealed, 'sealed prediction')}." if sealed else "."))
    if not notes:
        notes.append("Get your `/predict`ions in and your `/bingo` card ready.")
    log.info("[%s] %s lined up %r", ctx.guild.name, ctx.author, title)
    await ctx.send("\n".join([status_text(movie), *(f"-# {note}" for note in notes)]), allowed_mentions=NO_PINGS)


WATCHLIST_SHOWN = 30


@np_group.group(name="watchlist", fallback="show", invoke_without_command=True,
                description="Films to watch: added, imported from Letterboxd, or lined up and never started.")
async def np_watchlist(ctx: commands.Context):
    saved = watchlist(ctx.guild.id)
    if not saved:
        await ctx.send("🍿 The watchlist is empty. `/np watchlist add <title>`, `/np watchlist import <Letterboxd list>`, "
                       "or line something up and never start it.", ephemeral=True)
        return
    lines = []
    for movie in saved[:WATCHLIST_SHOWN]:
        sealed = sealed_count(movie.id)
        line = f"**{movie.linked_name}**, added by <@{movie.set_by}>"
        lines.append(line + (f", {plural(sealed, 'sealed prediction')}" if sealed else ""))
    if len(saved) > WATCHLIST_SHOWN:
        lines.append(f"…and {len(saved) - WATCHLIST_SHOWN} more.")
    embed = discord.Embed(title=f"🍿 To watch ({len(saved)})", description="\n".join(lines),
                          color=discord.Color.dark_red())
    embed.set_footer(text="Line one up with /np set <title> (it autocompletes); any predictions come with it.")
    await ctx.send(embed=embed, allowed_mentions=NO_PINGS)


@np_watchlist.command(name="add", description="Add a film to the watchlist.")
@app_commands.describe(title="The film")
async def np_watchlist_add(ctx: commands.Context, *, title: str):
    title = one_line(title, TITLE_MAX_LENGTH)
    if not title:
        await ctx.send("Add what?", ephemeral=True)
        return
    movie = add_to_watchlist(ctx.guild.id, title, ctx.author.id)
    if movie is None:
        await ctx.send(f"{discord.utils.escape_markdown(title)} is already on the watchlist.", ephemeral=True)
        return
    await ctx.send(f"🍿 Added **{movie.name}** to the watchlist ({len(watchlist(ctx.guild.id))} to watch).")


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


@np_watchlist.command(name="import", description="Add every film from a public Letterboxd list to the watchlist.")
@app_commands.describe(url="The list's address, e.g. https://letterboxd.com/someone/list/halloween/")
async def np_watchlist_import(ctx: commands.Context, url: str):
    await ctx.defer()  # Reading Letterboxd can take a few seconds.
    try:
        film_list = await letterboxd.fetch_list(url)
    except letterboxd.LetterboxdError as error:
        await ctx.send(f"🍿 {error}")
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
    await ctx.send(text + "\n-# `/np watchlist` to see them, `/np set <title>` to line one up.")


async def watchlist_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """/np set suggests the watchlist, but any title can still be typed."""
    typed = current.casefold()
    return [app_commands.Choice(name=f"{m.title} (watchlist)"[:100], value=m.title[:100])
            for m in watchlist(interaction.guild_id) if typed in m.title.casefold()][:25]


np_set.autocomplete("title")(watchlist_autocomplete)
np_watchlist_remove.autocomplete("title")(watchlist_autocomplete)


async def _ready_to_start(ctx: commands.Context) -> Movie | None:
    movie = current_movie(ctx.guild.id)
    if movie is None:
        await ctx.send("Nothing's lined up. `/np set <title>` first.", ephemeral=True)
    elif movie.started_at:
        await ctx.send(f"{movie.name} has already started.", ephemeral=True)
    elif ctx.guild.id in counting_down:
        await ctx.send("There's already a countdown going.", ephemeral=True)
    else:
        return movie
    return None


async def start_movie(ctx: commands.Context, movie: Movie) -> str:
    """Start it now, and return the announcement."""
    _update(movie.id, started_at=now(), watch_number=next_watch_number(ctx.guild.id, movie.title))
    movie = get_movie(movie.id)
    log.info("[%s] %s started %r", ctx.guild.name, ctx.author, movie.title)
    await set_bot_status(ctx.bot, movie.title)
    return (f"🎬 **Starting: {movie.label}.** Phones down, lights off.\n"
            f"-# {film_clock(movie)}. `/np pause` if you need to, `/shhh` if people won't be quiet.")


@np_group.command(name="start", description="Start the film that's lined up.")
async def np_start(ctx: commands.Context):
    movie = await _ready_to_start(ctx)
    if movie:
        await ctx.send(await start_movie(ctx, movie))


# Servers with a countdown running, so two can't start the film twice.
counting_down: set[int] = set()


@np_group.command(name="countdown",
                  description=f"Count down from {COUNTDOWN_FROM}, then start, so everyone presses play together.")
async def np_countdown(ctx: commands.Context):
    movie = await _ready_to_start(ctx)
    if movie is None:
        return
    counting_down.add(ctx.guild.id)
    try:
        # A Discord timestamp in the future counts itself down ("in 5 seconds", "in 4 seconds"...) on everyone's
        # screen, towards the same moment, so a message that arrives late doesn't make anyone late. Timestamps are
        # whole seconds, so it's the next whole second plus the countdown: between 5 and 6 seconds away.
        go_at = math.ceil(time.time()) + COUNTDOWN_FROM
        message = await ctx.send(f"# 🎬 {movie.label} starts <t:{go_at}:R>\n"
                                 "-# Get ready to press play. This changes to GO when it's time.")
        await asyncio.sleep(max(go_at - time.time(), 0))
        latest = current_movie(ctx.guild.id)
        if latest is None or latest.id != movie.id or latest.started_at:
            await _edit(message, "🎬 Countdown called off: the film changed or someone started it already.")
            return
        await _edit(message, "# ▶️ GO!\n" + await start_movie(ctx, latest))
    finally:
        counting_down.discard(ctx.guild.id)


async def _edit(message: discord.Message, content: str) -> None:
    try:
        await message.edit(content=content)
    except discord.HTTPException:
        pass  # The countdown message is gone or uneditable; the film has still started.


async def _playing(ctx: commands.Context) -> Movie | None:
    movie = current_movie(ctx.guild.id)
    if movie is None or movie.started_at is None:
        await ctx.send("Nothing's playing. " + ("`/np start` it first." if movie else "`/np set <title>` first."),
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
        await ctx.send("It's already paused. `/np resume` to carry on.", ephemeral=True)
        return
    _update(movie.id, paused_at=now())
    movie = current_movie(ctx.guild.id)
    reason = one_line(reason)
    text = f"⏸️ **Paused** {movie.name} at {timecode(watched_seconds(movie))}."
    if reason:
        text += f"\n> {reason}"
    await ctx.send(f"{text}\n-# Paused {live(movie.paused_at)}. `/np resume` to carry on.", allowed_mentions=NO_PINGS)
    await set_bot_status(ctx.bot, f"{movie.title} (paused)")


@np_group.command(name="sct", aliases=["seek"], usage="<time>",
                  description="Set current time: correct where the film is (e.g. 1:07:30), if the bot's clock is off.")
@app_commands.describe(position="Where the film is now: 1:07:30, 47:30, 1h 7m, 47m...")
async def np_sct(ctx: commands.Context, *, position: str):
    seconds = parse_timecode(position)
    if seconds is None:
        await ctx.send(f"I don't understand `{one_line(position, 50)}` as a time in the film. Try {TIMECODE_EXAMPLES}.",
                       ephemeral=True)
        return
    movie = current_movie(ctx.guild.id)
    if movie is None:
        await ctx.send("Nothing's lined up. `/np set <title>` first.", ephemeral=True)
        return
    note = ""
    if movie.started_at is None:  # Started without the bot: start it now, already that far in.
        if ctx.guild.id in counting_down:
            await ctx.send("There's a countdown going. Wait for it, then correct the time.", ephemeral=True)
            return
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
        text += "\n-# Still paused. `/np resume` to carry on."
    else:
        text += f"\n-# {film_clock(movie)}. Out of sync? `/np elapsed` to catch up."
    await ctx.send(text)


@np_group.command(name="elapsed", description="Exactly how far into the film we are, to get back in sync.")
async def np_elapsed(ctx: commands.Context):
    movie = await _playing(ctx)
    if movie is None:
        return
    if movie.paused_at:
        text = (f"⏸️ **{movie.label}** is paused at **{timecode(watched_seconds(movie))}**.\n"
                "-# Skip there, and press play when someone runs `/np resume`.")
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


@np_group.command(name="resume", description="Carry on after a pause.")
async def np_resume(ctx: commands.Context):
    movie = await _playing(ctx)
    if movie is None:
        return
    if not movie.paused_at:
        await ctx.send("It's not paused.", ephemeral=True)
        return
    paused_for = int((now() - movie.paused_at).total_seconds())
    _update(movie.id, paused_at=None, paused_seconds=movie.paused_seconds + paused_for)
    movie = get_movie(movie.id)
    text = f"▶️ **Resumed** {movie.name} at {timecode(watched_seconds(movie))}, after {duration(paused_for)}."
    if paused_for > LONG_PAUSE_SECONDS:
        text += f"\n-# {random.choice(LONG_PAUSE_LINES)}"
    await ctx.send(f"{text}\n-# {film_clock(movie)}.")
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
    text += "\n⭐ Rate it with `/rate <1-10>`."
    await ctx.send(text, allowed_mentions=NO_PINGS)
    await reveal_predictions(ctx.channel, movie)
    await set_bot_status(ctx.bot, None)


@np_group.command(name="history", description="What we've watched, and how it rated.")
async def np_history(ctx: commands.Context):
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
    embed.set_footer(text="See what was predicted for one with /np predictions <title> (add #2 for a second watch).")
    await ctx.send(embed=embed)


def verdict_line(verdict: Verdict) -> str:
    mark = "✅" if verdict.called else "❌" if verdict.no > verdict.yes else "⚖️"
    return f"{mark} <@{verdict.user_id}>: {verdict.text} ({verdict.yes}–{verdict.no})"


@np_group.command(name="predictions", description="What was predicted for a film we've watched, and who called it.")
@app_commands.describe(title="Which film (leave empty for the last one)")
async def np_predictions(ctx: commands.Context, *, title: str | None = None):
    movie = find_watched(ctx.guild.id, title)
    if movie is None:
        await ctx.send(f"No finished film called “{one_line(title, TITLE_MAX_LENGTH)}”. Try `/np history`."
                       if title else "🎬 Nothing watched yet.", ephemeral=True)
        return
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
    await ctx.send(embed=embed, allowed_mentions=NO_PINGS)


async def watched_title_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    typed = current.casefold()
    return [app_commands.Choice(name=f"{m.title} (watch #{m.watch_number or 1}, {m.ended_at.strftime('%d %b %Y')})"[:100],
                                value=f"id:{m.id}")
            for m in watched_movies(interaction.guild_id) if typed in m.title.casefold()][:25]


np_predictions.autocomplete("title")(watched_title_autocomplete)


# --- /shhh, /rate, /predict ---
@commands.hybrid_command(name="shhh", description="Tell everyone to be quiet for this bit.")
@commands.guild_only()
@app_commands.describe(reason="Optional: why this bit matters")
async def shhh(ctx: commands.Context, *, reason: str | None = None):
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


@commands.hybrid_command(name="rate", description="Rate the film out of 10, or see everyone's ratings.")
@commands.guild_only()
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


@commands.hybrid_command(name="predict", description="Make a sealed prediction about the film. Revealed at the end.")
@commands.guild_only()
@app_commands.describe(guess="What you think will happen")
async def predict(ctx: commands.Context, *, guess: str):
    movie = current_movie(ctx.guild.id)
    guess = one_line(guess)
    if movie is None:
        await ctx.send("Nothing's lined up to predict. `/np set <title>` first.", ephemeral=True)
        return
    if not guess:
        await ctx.send("Predict what?", ephemeral=True)
        return
    add_prediction(movie, ctx.author.id, guess)
    announcement = f"🔮 {ctx.author.mention} has made a sealed prediction about {movie.label}."
    if ctx.interaction:
        await ctx.send(announcement, allowed_mentions=NO_PINGS)
        await ctx.send(f"🔮 Sealed: {guess}\n-# Revealed when someone runs `/np end`.", ephemeral=True,
                       allowed_mentions=NO_PINGS)
        return
    try:
        await ctx.message.delete()  # Typed with !, so hide it until the reveal.
    except discord.HTTPException:
        announcement += "\n-# I couldn't hide your message (I need Manage Messages). Use `/predict` to keep it secret."
    await ctx.send(announcement, allowed_mentions=NO_PINGS)


# --- /bingo ---
async def _bingo_movie(ctx: commands.Context, need_started: bool) -> Movie | None:
    movie = current_movie(ctx.guild.id)
    if movie is None:
        await ctx.send("No film lined up. `/np set <title>` first.", ephemeral=True)
    elif need_started and movie.started_at is None:
        await ctx.send("No marking before it starts. Wait for `/np start`.", ephemeral=True)
    else:
        return movie
    return None


@commands.hybrid_group(name="bingo", description="Movie bingo: your card, and marking squares off.",
                       invoke_without_command=True)
@commands.guild_only()
async def bingo_group(ctx: commands.Context):
    await bingo_show.callback(ctx)


@bingo_group.command(name="card", description="See your bingo card for this film (only you can see it).")
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
        await ctx.send("I couldn't DM you. Use `/bingo card` instead.")


@bingo_group.command(name="mark", description="Mark off a square on your card.")
@app_commands.describe(square="The square's number on your card")
async def bingo_mark(ctx: commands.Context, square: commands.Range[int, 1, 25]):
    movie = await _bingo_movie(ctx, need_started=True)
    if movie is None:
        return
    marks = bingo_marks(movie.id, ctx.author.id)
    if square in marks:
        await ctx.send("That one's already marked." if square != BINGO_FREE else "That's the free space.", ephemeral=True)
        return
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


@bingo_group.command(name="unmark", description="Unmark a square you marked by mistake.")
@app_commands.describe(square="The square's number on your card")
async def bingo_unmark(ctx: commands.Context, square: commands.Range[int, 1, 25]):
    movie = await _bingo_movie(ctx, need_started=False)
    if movie is None:
        return
    if square == BINGO_FREE or square not in bingo_marks(movie.id, ctx.author.id):
        await ctx.send("That square isn't marked (or it's the free space).", ephemeral=True)
        return
    db.conn.execute("DELETE FROM movie_bingo_marks WHERE movie_id = ? AND user_id = ? AND square = ?",
                    (movie.id, ctx.author.id, square))
    db.conn.commit()
    await ctx.send(f"Unmarked square {square}. A bingo already called stays called.", ephemeral=True)


async def bingo_square_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
    movie = current_movie(interaction.guild_id)
    if movie is None:
        return []
    card, marks = bingo_card(movie.id, interaction.user.id), bingo_marks(movie.id, interaction.user.id)
    typed = current.casefold()
    choices = [app_commands.Choice(name=f"{n}. {square}"[:100], value=n) for n, square in enumerate(card, 1)
               if n not in marks and (typed in square.casefold() or typed == str(n))]
    return choices[:25]


bingo_mark.autocomplete("square")(bingo_square_autocomplete)


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    root = (command.root_parent or command).name
    if root not in ("np", "predict", "bingo", "rate"):
        return "", []
    text = ("1. `/np set <title>` lines it up. Nothing starts yet, so people can `/predict` and look at their "
            "`/bingo` card.\n"
            f"2. `/np start` starts it (the bot's status shows what's on), or `/np countdown` counts down from "
            f"{COUNTDOWN_FROM} first so everyone presses play together. `/np pause [reason]` and `/np resume` "
            "for breaks, which don't count towards the time watched. `/shhh` when people won't be quiet. Fallen out "
            "of sync? `/np elapsed` gives the exact spot and when to press play to catch up. Bot's clock wrong "
            "(restarted the film, started it without the bot)? `/np sct 1:07:30` sets where it really is.\n"
            "3. `/bingo mark <number>` as things happen. Five in a row wins.\n"
            f"4. `/np end` reveals the predictions: react {CALLED_IT} if they called it, {NOT_IT} if not "
            "(not on your own). Then everyone `/rate`s it.\n"
            "• Anyone can run any of it. Called predictions and bingo wins go on the rap sheet; `/np history` "
            "lists what you've watched with its ratings, and `/np predictions <title>` shows what was predicted "
            "for a film and who called it.\n"
            "• `/np watchlist` is what's still to watch: `add` a film, `import` a public Letterboxd list (with "
            "years and links), `remove` one. Films swapped out with `/np set` or ended before they started go "
            "on it too, with their predictions. `/np set` autocompletes from it; `Alien` finds `Alien (1979)`.\n"
            "• Watching something again is a new watch (Alien (watch #2)), with fresh predictions, bingo cards and "
            "ratings. `/np predictions Alien #1` looks up an earlier one.")
    return "", [("🎬 How movie night works", text, False)]


async def setup(bot: commands.Bot):
    for command in (np_group, shhh, rate, predict, bingo_group):
        bot.add_command(command)
    bot.add_listener(prediction_vote, "on_raw_reaction_add")
    bot.add_listener(prediction_unvote, "on_raw_reaction_remove")
