"""The shared game engine behind /play: one lobby and session system that every game plugs into.

A game (a Game subclass, registered with register()) only knows its own rules: who's on which side, what's on each
player's card, what it's waiting for, what an answer does, and how it ends. This module does everything around
that, the same for every game:

- the lobby: one message, edited in place (Join, Leave, Start, the pace, Cancel), which becomes the game's board;
- two paces, picked in the lobby: **live** (everyone together: deadlines in seconds) and **async** (through the day:
  hours per move, and the clock stops in QUIET hours, BOT_TIMEZONE, so nobody's timed out while asleep, though moves
  are still taken then);
- private cards and moves, by buttons on the board (🃏 My card, ✍️ Your move): a card or a question only the presser
  sees, as a reply to their press, never a DM;
- deadlines, reminders (async) and turn notices, which only ping players who've asked to be (🔔: game_pings), so a
  muted channel stays muted;
- joining mid-game (➕ Join next round: game_waiting), dealt in when the next round's lobby opens;
- the board kept in sight: after the game posts, or when chat has buried it, it's posted again at the bottom (and
  the old one deleted), rather than pinned (pinning needs Manage Messages and posts a notice of its own);
- the reveal, Play again (same players and whoever's waiting, a fresh lobby), and every result kept in game_results for all-time tables
  later (nothing shows them yet: a game's results show only until the next one).

Everything's in the database (game_sessions, game_players) and every button is a lasting one ("game:<id>:<action>",
read back by GameButton, a DynamicItem), so a restart mid-game just carries on. deadline_loop checks every few
seconds; if Discord can't be reached it tries again (common.UNREACHABLE), and a broken game is logged and ended
rather than stopping everyone else's. One game per channel at a time.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone

import discord
from discord.ext import tasks

from ktdi import common, config, db
from ktdi.common import NO_PINGS, log

PACES = {"live": "⚡ Live", "async": "🕰️ Through the day"}
QUIET = (time(23, 0), time(7, 0))  # Async deadlines don't run between these, where the bot is
LOBBY_LIFE = {"live": timedelta(minutes=15), "async": timedelta(hours=24)}  # A lobby nobody starts goes
NUDGE_AT = 0.75  # Async: remind whoever's being waited on this far through their time
CHECK_EVERY = 5  # Seconds between deadline checks
ACTIVE = ("lobby", "playing")
COLOUR = discord.Color.from_rgb(120, 90, 160)
BUMP_AFTER = 5  # Chat messages under the board before it's moved back to the bottom...
BUMP_GAP = timedelta(seconds=30)  # ...at most this often


def now() -> datetime:
    return datetime.now(timezone.utc)


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


# --- Time that counts: async deadlines skip the quiet hours ---
def quiet_until(moment: datetime) -> datetime | None:
    """If it's quiet hours (where the bot is) at this moment, when they end; otherwise None."""
    local = moment.astimezone(config.BOT_TIMEZONE)
    start, end = QUIET
    if local.time() >= start:  # Late evening: quiet until tomorrow morning
        return datetime.combine(local.date() + timedelta(days=1), end, config.BOT_TIMEZONE).astimezone(timezone.utc)
    if local.time() < end:  # Small hours: quiet until this morning
        return datetime.combine(local.date(), end, config.BOT_TIMEZONE).astimezone(timezone.utc)
    return None


def after(start: datetime, seconds: float, pace: str) -> datetime:
    """When `seconds` of the game's time have passed since `start`: just that, live; async, not counting quiet hours
    (the clock stops at 23:00 and starts again at 07:00)."""
    if pace != "async":
        return start + timedelta(seconds=seconds)
    moment, left = start, timedelta(seconds=seconds)
    while True:
        if until := quiet_until(moment):
            moment = until
        local = moment.astimezone(config.BOT_TIMEZONE)
        quiet_starts = datetime.combine(local.date(), QUIET[0], config.BOT_TIMEZONE).astimezone(timezone.utc)
        if moment + left <= quiet_starts:
            return moment + left
        left -= quiet_starts - moment
        moment = quiet_starts


# --- What games are made of ---
@dataclass
class Ask:
    """What a player's move asks of them: a word or two typed into a form ("text"), or one of some choices
    ("choice": (label, value) pairs)."""
    prompt: str
    kind: str = "text"
    choices: list[tuple[str, str]] = field(default_factory=list)
    max_length: int = 40
    placeholder: str = ""


@dataclass
class Result:
    """What an answer did: `reply` is just for the player (a thanks, or why it can't be that), `posts` are for the
    channel. `ok` is False for an answer that doesn't count (try again)."""
    reply: str = ""
    posts: list[str | discord.Embed] = field(default_factory=list)
    ok: bool = True


class Game:
    """A game's rules. A subclass sets the class attributes and the methods below; the engine calls them with the
    Session (whose `state` dict is the game's own, saved after every change)."""
    key = ""  # "crust": what /play game: takes, and what the database keeps
    title = ""
    emoji = "🎲"
    blurb = ""  # A line for the lobby
    rules = ""  # A few lines for the lobby and /help
    min_players, max_players = 3, 10
    paces = ("live", "async")
    timings: dict[str, dict[str, float]] = {}  # pace -> what's being waited for (Step.kind) -> seconds

    def deal(self, session: "Session") -> None:
        """Set up a game for these players: who's who, what's on each card. Called once, at the start."""
        raise NotImplementedError

    def card(self, session: "Session", user_id: int) -> discord.Embed:
        """A player's private card (🃏 My card)."""
        raise NotImplementedError

    def step(self, session: "Session") -> tuple[str, str]:
        """What it's waiting for now, as (a key unique to this step, its kind for `timings`): ("clue:123", "clue").
        A new key starts a new deadline."""
        raise NotImplementedError

    def waiting_on(self, session: "Session") -> list[int]:
        """Who it's waiting for now (the ones nudged and pinged)."""
        raise NotImplementedError

    def status(self, session: "Session") -> str:
        """A line or two for the board: what's happening (never anything private)."""
        raise NotImplementedError

    def move_button(self, session: "Session") -> tuple[str, str]:
        """The move button's label and emoji now, so it says what to do ("Vote", not just "Your move")."""
        return "Your move", "✍️"

    def ask(self, session: "Session", user_id: int) -> Ask | str:
        """What ✍️ Your move asks this player now, or (a str) why there's nothing for them to do."""
        raise NotImplementedError

    def answer(self, session: "Session", user_id: int, value: str) -> Result:
        """A player's answer to ask()."""
        raise NotImplementedError

    def timeout(self, session: "Session") -> list[str | discord.Embed]:
        """The step's deadline passed: move on (a skipped turn, a vote with the votes in), returning any posts."""
        raise NotImplementedError

    def finished(self, session: "Session") -> bool:
        raise NotImplementedError

    def reveal(self, session: "Session") -> discord.Embed:
        """The end: the truth, the answers, the points, and where it all came from."""
        raise NotImplementedError

    def results(self, session: "Session") -> dict[int, tuple[int, bool, str]]:
        """Each player's (points, won, role), for game_results."""
        raise NotImplementedError


GAMES: dict[str, Game] = {}


def register(game: Game) -> Game:
    GAMES[game.key] = game
    return game


# --- Sessions ---
@dataclass
class Session:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    game_key: str
    host_id: int
    pace: str
    phase: str
    step: str | None
    state: dict
    deadline: datetime | None
    nudge_at: datetime | None
    starts_at: datetime | None
    players: list[int] = field(default_factory=list)  # In the order they joined

    @property
    def game(self) -> Game:
        return GAMES[self.game_key]


COLUMNS = ("id, guild_id, channel_id, message_id, game, host_id, pace, phase, step, state, deadline, nudge_at, "
           "starts_at")


def _session(row) -> Session | None:
    if row is None:
        return None
    values = list(row)
    values[9] = json.loads(values[9])
    values[10:13] = [_time(v) for v in values[10:13]]
    session = Session(*values)
    session.players = [user for (user,) in db.conn.execute(
        "SELECT user_id FROM game_players WHERE session_id = ? ORDER BY joined_at, rowid", (session.id,))]
    return session


def get(session_id: int) -> Session | None:
    return _session(db.conn.execute(f"SELECT {COLUMNS} FROM game_sessions WHERE id = ?", (session_id,)).fetchone())


def active_in(channel_id: int) -> Session | None:
    """The game going on in a channel (in its lobby or being played), if there is one."""
    return _session(db.conn.execute(
        f"SELECT {COLUMNS} FROM game_sessions WHERE channel_id = ? AND phase IN ('lobby', 'playing') "
        "ORDER BY id DESC", (channel_id,)).fetchone())


def create(guild_id: int, channel_id: int, game: Game, host_id: int, pace: str, players: list[int],
           starts_at: datetime | None = None) -> Session:
    moment = now()
    deadline = starts_at or moment + LOBBY_LIFE[pace]
    session_id = db.conn.execute(
        "INSERT INTO game_sessions (guild_id, channel_id, game, host_id, pace, phase, deadline, starts_at, created_at, "
        "updated_at) VALUES (?, ?, ?, ?, ?, 'lobby', ?, ?, ?, ?)",
        (guild_id, channel_id, game.key, host_id, pace, deadline.isoformat(),
         starts_at.isoformat() if starts_at else None, moment.isoformat(), moment.isoformat())).lastrowid
    for user_id in players:
        add_player(session_id, user_id, commit=False)
    db.conn.commit()
    return get(session_id)


def add_player(session_id: int, user_id: int, commit: bool = True) -> None:
    db.conn.execute("INSERT OR IGNORE INTO game_players (session_id, user_id, joined_at) VALUES (?, ?, ?)",
                    (session_id, user_id, now().isoformat()))
    if commit:
        db.conn.commit()


def waiting_list(session_id: int) -> list[int]:
    """Who's joined mid-game, for the next round, in the order they joined."""
    return [user for (user,) in db.conn.execute(
        "SELECT user_id FROM game_waiting WHERE session_id = ? ORDER BY joined_at, rowid", (session_id,))]


def add_waiting(session_id: int, user_id: int) -> None:
    db.conn.execute("INSERT OR IGNORE INTO game_waiting (session_id, user_id, joined_at) VALUES (?, ?, ?)",
                    (session_id, user_id, now().isoformat()))
    db.conn.commit()


def remove_player(session_id: int, user_id: int) -> None:
    db.conn.execute("DELETE FROM game_players WHERE session_id = ? AND user_id = ?", (session_id, user_id))
    db.conn.commit()


def save(session: Session) -> None:
    db.conn.execute(
        "UPDATE game_sessions SET message_id = ?, host_id = ?, pace = ?, phase = ?, step = ?, state = ?, deadline = ?, "
        "nudge_at = ?, starts_at = ?, updated_at = ?, ended_at = CASE WHEN ? IN ('lobby', 'playing') THEN NULL "
        "ELSE COALESCE(ended_at, ?) END WHERE id = ?",
        (session.message_id, session.host_id, session.pace, session.phase, session.step, json.dumps(session.state),
         session.deadline.isoformat() if session.deadline else None,
         session.nudge_at.isoformat() if session.nudge_at else None,
         session.starts_at.isoformat() if session.starts_at else None, now().isoformat(), session.phase,
         now().isoformat(), session.id))
    db.conn.commit()


def pings_on(user_id: int) -> bool:
    return db.conn.execute("SELECT 1 FROM game_pings WHERE user_id = ?", (user_id,)).fetchone() is not None


def toggle_pings(user_id: int) -> bool:
    """Turn a player's move pings on (or off again). Returns whether they're on now."""
    if pings_on(user_id):
        db.conn.execute("DELETE FROM game_pings WHERE user_id = ?", (user_id,))
    else:
        db.conn.execute("INSERT INTO game_pings (user_id) VALUES (?)", (user_id,))
    db.conn.commit()
    return pings_on(user_id)


_locks: dict[int, asyncio.Lock] = {}


def lock(session_id: int) -> asyncio.Lock:
    """One change to a game at a time (two people pressing at once, or a deadline as someone answers)."""
    return _locks.setdefault(session_id, asyncio.Lock())


# --- What's shown ---
def name_of(session: Session, user_id: int) -> str:
    """A player's name in the server, for menus (which can't show mentions): "Player 2" if Discord hasn't said."""
    get_guild = getattr(common.bot, "get_guild", None)
    guild = get_guild(session.guild_id) if get_guild else None
    member = guild.get_member(user_id) if guild else None
    if member is not None:
        return member.display_name
    return f"Player {session.players.index(user_id) + 1}" if user_id in session.players else "Someone"


def mentions(user_ids: list[int]) -> str:
    names = [f"<@{user}>" for user in user_ids]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}" if names else "nobody"


def lobby_embed(session: Session) -> discord.Embed:
    game = session.game
    lines = [game.blurb, "", f"**Pace:** {PACES[session.pace]}"
             + (" (4-hour moves; the clock stops overnight)" if session.pace == "async" else ""),
             f"**Players ({len(session.players)}/{game.max_players}, {game.min_players} needed):** "
             + (" ".join(f"<@{user}>" for user in session.players) or "nobody yet"),
             f"**Host:** <@{session.host_id}>"]
    if session.starts_at:
        lines.append(f"**Starts** <t:{int(session.starts_at.timestamp())}:R> with whoever's in")
    if game.rules:
        lines += ["", game.rules]
    embed = discord.Embed(title=f"{game.emoji} {game.title}: join in", description="\n".join(lines), color=COLOUR)
    embed.set_footer(text="Join, then the host starts it. 🔔 to be pinged when it's your move (otherwise you won't be).")
    return embed


def board_embed(session: Session) -> discord.Embed:
    game = session.game
    lines = [game.status(session)]
    waiting = game.waiting_on(session)
    if waiting:
        lines.append(f"**Waiting on:** {mentions(waiting)}")
    if session.deadline:
        lines.append(f"**Time's up** <t:{int(session.deadline.timestamp())}:R>")
    if session.phase == "playing" and (next_round := waiting_list(session.id)):
        lines.append(f"**Next round:** {' '.join(f'<@{user}>' for user in next_round)}")
    lines.append(f"-# {PACES[session.pace]} · players: {' '.join(f'<@{user}>' for user in session.players)}")
    return discord.Embed(title=f"{game.emoji} {game.title}", description="\n".join(lines), color=COLOUR)


def view_for(session: Session) -> discord.ui.View | None:
    view = discord.ui.View(timeout=None)
    buttons = {"lobby": ["join", "leave", "start", "pace", "pings", "cancel"],
               "playing": ["card", "move", "join", "pings", "cancel"],
               "done": ["again"]}.get(session.phase, [])
    for action in buttons:
        if action == "pace" and len(session.game.paces) < 2:
            continue
        if action == "move" and session.phase == "playing":
            label, emoji = session.game.move_button(session)
            view.add_item(GameButton(session.id, action, label=label, emoji=emoji))
        elif action == "join" and session.phase == "playing":
            view.add_item(GameButton(session.id, action, label="Join next round"))
        else:
            view.add_item(GameButton(session.id, action))
    return view if buttons else None


async def update_board(session: Session) -> None:
    """Edit the lobby/board message to how things are now."""
    channel = common.bot.get_channel(session.channel_id) if common.bot else None
    if channel is None or session.message_id is None:
        return
    try:
        await channel.get_partial_message(session.message_id).edit(embed=board_for(session), view=view_for(session))
    except (discord.HTTPException, KeyError):
        pass  # The board's gone (deleted?): the game goes on, in its posts


def board_for(session: Session) -> discord.Embed:
    return lobby_embed(session) if session.phase == "lobby" else ended_embed(session) \
        if session.phase in ("cancelled", "expired") else board_embed(session)


_buried: dict[int, int] = {}  # Channel -> chat messages since its board was last posted
_bumped: dict[int, datetime] = {}  # Channel -> when its board was last moved down


async def bump(session: Session) -> None:
    """Move the board to the bottom of the channel, so it isn't lost in chat: post it again, and delete the old one
    (its buttons are lasting ones, so a press on it on the way out still works)."""
    channel = common.bot.get_channel(session.channel_id) if common.bot else None
    if channel is None:
        return
    old = session.message_id
    try:
        message = await channel.send(embed=board_for(session), view=view_for(session), allowed_mentions=NO_PINGS)
    except discord.HTTPException:
        await update_board(session)  # Can't post (permissions?): the old one's kept up to date instead
        return
    session.message_id = message.id
    save(session)
    _buried[session.channel_id], _bumped[session.channel_id] = 0, now()
    if old is not None:
        try:
            await channel.get_partial_message(old).delete()
        except (discord.HTTPException, KeyError):
            pass  # Already gone


async def chatted(message: discord.Message) -> None:
    """on_message: when chat has buried a game's board (BUMP_AFTER messages, BUMP_GAP apart at most), move it down."""
    me = getattr(getattr(common.bot, "user", None), "id", None)
    if message.guild is None or message.author.id == me:  # The game's own posts are followed by the board anyway
        return
    channel_id = message.channel.id
    _buried[channel_id] = _buried.get(channel_id, 0) + 1
    last = _bumped.get(channel_id)
    if _buried[channel_id] < BUMP_AFTER or (last and now() - last < BUMP_GAP):
        return
    session = active_in(channel_id)
    if session is None:
        _buried.pop(channel_id, None)
        return
    async with lock(session.id):
        session = get(session.id)
        if session is not None and session.phase in ACTIVE and session.message_id is not None:
            await bump(session)


def ended_embed(session: Session) -> discord.Embed:
    why = "cancelled" if session.phase == "cancelled" else "abandoned: nobody did anything for too long"
    return discord.Embed(title=f"{session.game.emoji} {session.game.title}", description=f"This game was {why}.",
                         color=discord.Color.dark_grey())


async def post(session: Session, items: list[str | discord.Embed], pinged: list[int] = ()) -> None:
    """Post to the game's channel: only the players in `pinged` who've asked for pings are notified."""
    channel = common.bot.get_channel(session.channel_id) if common.bot else None
    if channel is None:
        return
    ping = [discord.Object(id=user) for user in pinged if pings_on(user)]
    allowed = discord.AllowedMentions(users=ping, everyone=False, roles=False) if ping else NO_PINGS
    for item in items:
        if isinstance(item, discord.Embed):
            await channel.send(embed=item, allowed_mentions=NO_PINGS)
        else:
            await channel.send(item, allowed_mentions=allowed)


# --- Moving the game along ---
async def start(session: Session) -> None:
    """Deal, and start the clock on the first move."""
    session.phase, session.step, session.starts_at = "playing", None, None
    session.game.deal(session)
    log.info("A game of %s started in channel %s (%d players, %s)", session.game_key, session.channel_id,
             len(session.players), session.pace)
    await advanced(session, [f"{session.game.emoji} **{session.game.title} has started.** Press 🃏 **My card** on "
                             f"the board to see yours (only you will)."])


async def advanced(session: Session, posts: list[str | discord.Embed]) -> None:
    """After any change: save it, start a new deadline if it's moved on a step (with a turn notice), and finish it if
    it's over."""
    game = session.game
    if session.phase == "playing" and game.finished(session):
        await post(session, posts)
        await finish(session)
        return
    if session.phase == "playing":
        key, kind = game.step(session)
        if key != session.step:
            session.step = key
            seconds = game.timings[session.pace][kind]
            started = now()
            session.deadline = after(started, seconds, session.pace)
            session.nudge_at = after(started, seconds * NUDGE_AT, session.pace) if session.pace == "async" else None
            waiting = game.waiting_on(session)
            if waiting and (session.pace == "async" or any(pings_on(user) for user in waiting)):
                label, emoji = game.move_button(session)
                posts = posts + [f"⏳ {mentions(waiting)}: {game.status(session)} Press {emoji} **{label}** on the "
                                 f"board. Time's up <t:{int(session.deadline.timestamp())}:R>."]
            save(session)
            await post(session, posts, pinged=waiting)
            await (bump(session) if posts else update_board(session))
            return
    save(session)
    await post(session, posts)
    await (bump(session) if posts else update_board(session))


async def finish(session: Session) -> None:
    session.phase, session.step, session.deadline, session.nudge_at = "done", None, None, None
    save(session)
    moment = now().isoformat()
    for user_id, (points, won, role) in session.game.results(session).items():
        db.conn.execute("INSERT OR REPLACE INTO game_results (session_id, guild_id, game, user_id, points, won, role, "
                        "at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (session.id, session.guild_id, session.game_key, user_id, points, int(won), role, moment))
    db.conn.commit()
    log.info("A game of %s finished in channel %s", session.game_key, session.channel_id)
    channel = common.bot.get_channel(session.channel_id) if common.bot else None
    if channel is not None:
        next_round = waiting_list(session.id)
        joining = (f"🔁 Waiting for the next round: {' '.join(f'<@{user}>' for user in next_round)}. Press **Play "
                   f"again** to deal them in.") if next_round else None
        await channel.send(joining, embed=session.game.reveal(session), view=view_for(session),
                           allowed_mentions=NO_PINGS)
    await update_board(session)


async def end(session: Session, phase: str) -> None:
    """Cancelled, or expired: it's over, with nothing to reveal."""
    session.phase, session.step, session.deadline, session.nudge_at = phase, None, None, None
    save(session)
    await update_board(session)


# --- The buttons ---
ACTIONS = {  # action -> (label, emoji, style)
    "join": ("Join", "➕", discord.ButtonStyle.success), "leave": ("Leave", "➖", discord.ButtonStyle.secondary),
    "start": ("Start", "▶️", discord.ButtonStyle.primary), "pace": ("Pace", "🕰️", discord.ButtonStyle.secondary),
    "pings": ("Ping me", "🔔", discord.ButtonStyle.secondary), "cancel": ("Cancel", "✖️", discord.ButtonStyle.danger),
    "card": ("My card", "🃏", discord.ButtonStyle.primary), "move": ("Your move", "✍️", discord.ButtonStyle.success),
    "again": ("Play again", "🔁", discord.ButtonStyle.primary),
}


class GameButton(discord.ui.DynamicItem[discord.ui.Button], template=r"game:(?P<session>[0-9]+):(?P<action>[a-z]+)"):
    def __init__(self, session_id: int, action: str, label: str | None = None, emoji: str | None = None):
        default_label, default_emoji, style = ACTIONS[action]
        label, emoji = label or default_label, emoji or default_emoji
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=style,
                                           custom_id=f"game:{session_id}:{action}"))
        self.session_id, self.action = session_id, action

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(int(match["session"]), match["action"])

    async def callback(self, interaction: discord.Interaction):
        await pressed(interaction, self.session_id, self.action)


async def reply(interaction: discord.Interaction, text: str = "", **kwargs) -> None:
    await interaction.response.send_message(text, ephemeral=True, allowed_mentions=NO_PINGS, **kwargs)


def can_manage(interaction: discord.Interaction, session: Session) -> bool:
    permissions = getattr(interaction.user, "guild_permissions", None)
    return interaction.user.id == session.host_id or bool(permissions and permissions.manage_guild)


async def pressed(interaction: discord.Interaction, session_id: int, action: str) -> None:
    """Every game button comes here."""
    user = interaction.user.id
    if action == "pings":
        on = toggle_pings(user)
        await reply(interaction, "🔔 You'll be pinged when it's your move, in every game." if on else
                    "🔕 No more pings: you'll still see whose move it is on the board.")
        return
    if action == "move":  # Its own path: it may need a form or a choice, before anything changes
        await ask(interaction, session_id)
        return
    async with lock(session_id):
        session = get(session_id)
        if session is None:
            await reply(interaction, "That game's gone.")
            return
        game = session.game
        if action == "again":
            await play_again(interaction, session)
            return
        if action == "card":
            if session.phase != "playing":
                await reply(interaction, "There are no cards: the game isn't on.")
            elif user not in session.players:
                await reply(interaction, "You're not in this one. Watch, and join the next.")
            else:
                await reply(interaction, embed=game.card(session, user))
            return
        if action == "join" and session.phase == "playing":
            await join_next_round(interaction, session)
            return
        if session.phase != "lobby" and action in ("join", "leave", "start", "pace"):
            await reply(interaction, "That lobby's closed: the game's started (or over).")
            return
        if action == "join":
            if user in session.players:
                await reply(interaction, "You're already in.")
                return
            if len(session.players) >= game.max_players:
                await reply(interaction, f"It's full: {game.max_players} at most.")
                return
            add_player(session.id, user)
        elif action == "leave":
            if user not in session.players:
                await reply(interaction, "You're not in it.")
                return
            remove_player(session.id, user)
            session = get(session.id)
            if user == session.host_id:  # The host's gone: the next to join takes over, or it's over
                if not session.players:
                    await end(session, "cancelled")
                    await interaction.response.defer()
                    return
                session.host_id = session.players[0]
                save(session)
        elif action == "pace":
            if not can_manage(interaction, session):
                await reply(interaction, "Only the host can change the pace.")
                return
            session.pace = "async" if session.pace == "live" else "live"
            session.deadline = session.starts_at or now() + LOBBY_LIFE[session.pace]
            save(session)
        elif action == "cancel":
            if not can_manage(interaction, session):
                await reply(interaction, "Only the host (or someone with Manage Server) can cancel it.")
                return
            await end(session, "cancelled")
            await reply(interaction, "Cancelled.")
            return
        elif action == "start":
            if not can_manage(interaction, session):
                await reply(interaction, "Only the host can start it.")
                return
            if len(session.players) < game.min_players:
                await reply(interaction, f"It needs {game.min_players} players: {len(session.players)} so far.")
                return
            await interaction.response.defer()
            await start(session)
            return
        session = get(session.id)
        await interaction.response.edit_message(embed=lobby_embed(session), view=view_for(session))


async def join_next_round(interaction: discord.Interaction, session: Session) -> None:
    """➕ mid-game: on the list for the next round, dealt in when its lobby opens (Play again)."""
    user = interaction.user.id
    if user in session.players:
        await reply(interaction, "You're in this round already.")
        return
    next_round = waiting_list(session.id)
    if user in next_round:
        await reply(interaction, "You're in for the next round already.")
        return
    if len(session.players) + len(next_round) >= session.game.max_players:
        await reply(interaction, f"The next round's full: {session.game.max_players} at most.")
        return
    add_waiting(session.id, user)
    await reply(interaction, "➕ You're in for the next round: you'll be dealt in when this one's over and someone "
                             "presses 🔁 **Play again**. Watch this one for how they play.")
    await update_board(session)


async def ask(interaction: discord.Interaction, session_id: int) -> None:
    """✍️ Your move: the game's question, as a form or a choice; the answer goes to answered()."""
    session = get(session_id)
    if session is None or session.phase != "playing":
        await reply(interaction, "There's nothing to do: the game isn't on.")
        return
    if interaction.user.id not in session.players:
        await reply(interaction, "You're not in this one.")
        return
    question = session.game.ask(session, interaction.user.id)
    if isinstance(question, str):
        await reply(interaction, question)
    elif question.kind == "text":
        await interaction.response.send_modal(AnswerForm(session, question))
    else:
        view = discord.ui.View(timeout=600)
        view.add_item(AnswerChoice(session, question))
        await reply(interaction, question.prompt, view=view)


class AnswerForm(discord.ui.Modal):
    """A typed answer (a clue)."""

    def __init__(self, session: Session, question: Ask):
        super().__init__(title=f"{session.game.title}: your move"[:45])
        self.session_id, self.step = session.id, session.step
        self.text = discord.ui.TextInput(label=question.prompt[:45], max_length=question.max_length,
                                         placeholder=question.placeholder[:100] or None)
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction):
        await answered(interaction, self.session_id, self.step, self.text.value)


class AnswerChoice(discord.ui.Select):
    """A chosen answer (a vote, a guess)."""

    def __init__(self, session: Session, question: Ask):
        super().__init__(placeholder=question.prompt[:150],
                         options=[discord.SelectOption(label=label[:100], value=value[:100])
                                  for label, value in question.choices[:25]])
        self.session_id, self.step = session.id, session.step

    async def callback(self, interaction: discord.Interaction):
        await answered(interaction, self.session_id, self.step, self.values[0])


async def answered(interaction: discord.Interaction, session_id: int, step: str | None, value: str) -> None:
    """An answer: given to the game, if it's still the step it was asked for."""
    async with lock(session_id):
        session = get(session_id)
        if session is None or session.phase != "playing" or session.step != step:
            await reply(interaction, "Too late: the game's moved on.")
            return
        result = session.game.answer(session, interaction.user.id, value.strip())
        await reply(interaction, result.reply or ("✅ Done." if result.ok else "That won't do."))
        if result.ok:
            await advanced(session, result.posts)


async def play_again(interaction: discord.Interaction, session: Session) -> None:
    """🔁 Play again: a fresh lobby, same game, same pace, everyone still in (anyone can leave)."""
    if session.phase != "done":
        await reply(interaction, "That one isn't over yet.")
        return
    if going := active_in(session.channel_id):
        await reply(interaction, f"There's already a game here: {going.game.title}.")
        return
    everyone = [interaction.user.id] + [user for user in session.players + waiting_list(session.id)
                                        if user != interaction.user.id]
    again = create(session.guild_id, session.channel_id, session.game, interaction.user.id, session.pace,
                   list(dict.fromkeys(everyone))[:session.game.max_players])
    await interaction.response.defer()
    channel = common.bot.get_channel(again.channel_id) if common.bot else None
    if channel is not None:
        message = await channel.send(embed=lobby_embed(again), view=view_for(again), allowed_mentions=NO_PINGS)
        again.message_id = message.id
        save(again)


# --- Deadlines ---
async def tick(moment: datetime) -> None:
    """Everything that's due: lobbies to start or close, reminders, and moves out of time."""
    rows = db.conn.execute(
        "SELECT id FROM game_sessions WHERE phase IN ('lobby', 'playing') AND ((deadline IS NOT NULL AND deadline <= ?) "
        "OR (nudge_at IS NOT NULL AND nudge_at <= ?))", (moment.isoformat(), moment.isoformat())).fetchall()
    for (session_id,) in rows:
        async with lock(session_id):
            session = get(session_id)
            if session is None or session.phase not in ACTIVE:
                continue
            try:
                await due(session, moment)
            except common.UNREACHABLE as error:  # No network: it'll be due again next time round
                log.warning("Couldn't reach Discord for game %d (%s): trying again shortly", session_id, error)
            except Exception:  # A broken game is ended (and logged), not left to break every few seconds
                log.exception("Game %d failed: ending it", session_id)
                await end(session, "expired")


async def due(session: Session, moment: datetime) -> None:
    if session.phase == "lobby":
        if session.starts_at and len(session.players) >= session.game.min_players:
            await start(session)
        else:
            if session.starts_at:
                await post(session, [f"{session.game.emoji} Not enough players for {session.game.title} "
                                     f"({session.game.min_players} needed). Maybe next time."])
            await end(session, "expired")
        return
    if session.nudge_at and session.nudge_at <= moment and (not session.deadline or session.deadline > moment):
        session.nudge_at = None
        save(session)
        waiting = session.game.waiting_on(session)
        if waiting:
            await post(session, [f"⏰ {mentions(waiting)}: still your move in {session.game.title}. Time's up "
                                 f"<t:{int(session.deadline.timestamp())}:R>."], pinged=waiting)
            await bump(session)
        return
    if session.deadline and session.deadline <= moment:
        stuck_at = session.step
        await advanced(session, session.game.timeout(session))
        session = get(session.id)
        if session.phase == "playing" and session.step == stuck_at:  # A game must move on when time's up
            log.error("Game %d didn't move on from %s when its time ran out: ending it", session.id, stuck_at)
            await end(session, "expired")


@tasks.loop(seconds=CHECK_EVERY)
async def deadline_loop():
    await tick(now())


@deadline_loop.before_loop
async def before_deadline_loop():
    await common.bot.wait_until_ready()


def start_loop() -> None:
    if not deadline_loop.is_running():
        deadline_loop.start()
