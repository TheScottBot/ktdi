"""The game engine behind /play (ktdi.sessions): lobbies, both paces, private cards and moves, deadlines (with
async's quiet hours), pings only for those who asked, restarts, and the reveal. Tested with a tiny game of its own,
so the engine's checked apart from any real game's rules."""

import types
from datetime import datetime, timedelta, timezone

import discord
import pytest

from ktdi import db, sessions
from ktdi.features import play
from tests.fakes import Channel, Ctx, Guild, Interaction, User, run

SCOTT, DAVE, PAT, AMY = User(1, "scott"), User(2, "dave"), User(3, "pat"), User(4, "amy")
NOON = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)  # Monday, 12:00 in London (GMT)


class Words(sessions.Game):
    """Each player says a word, in the order they joined. Everyone who says one scores a point."""
    key, title, emoji, blurb = "words", "Words", "🔤", "Say a word."
    min_players, max_players = 2, 4
    timings = {"live": {"word": 30}, "async": {"word": 4 * 3600}}

    def deal(self, session):
        session.state = {"turn": 0, "said": {}}

    def card(self, session, user_id):
        return discord.Embed(title=f"Your card, {user_id}")

    def step(self, session):
        return f"word:{session.state['turn']}", "word"

    def waiting_on(self, session):
        turn = session.state["turn"]
        return [session.players[turn]] if turn < len(session.players) else []

    def status(self, session):
        return f"{len(session.state['said'])} words said."

    def ask(self, session, user_id):
        if self.waiting_on(session) != [user_id]:
            return "Not your turn."
        return sessions.Ask("A word")

    def answer(self, session, user_id, value):
        if " " in value:
            return sessions.Result("One word.", ok=False)
        session.state["said"][str(user_id)] = value
        session.state["turn"] += 1
        return sessions.Result("Thanks.", [f"<@{user_id}> said {value}"])

    def timeout(self, session):
        session.state["turn"] += 1
        return ["Too slow."]

    def finished(self, session):
        return session.state["turn"] >= len(session.players)

    def reveal(self, session):
        return discord.Embed(title="The words", description=" ".join(session.state["said"].values()))

    def results(self, session):
        return {user: (1 if str(user) in session.state["said"] else 0, str(user) in session.state["said"], "talker")
                for user in session.players}


@pytest.fixture(autouse=True)
def game(monkeypatch, clock, bot):
    monkeypatch.setitem(sessions.GAMES, "words", Words())
    monkeypatch.setattr(sessions, "_buried", {})
    monkeypatch.setattr(sessions, "_bumped", {})
    clock.set(NOON, sessions)
    bot.add_channel(Channel(500, Guild(111)))
    return clock


def channel(bot):
    return bot.channels[500]


def open_lobby(user=SCOTT, pace="live", start=None, game="words"):
    ctx = Ctx(user, Guild(111), channel=None)
    from ktdi import common
    ctx.channel = common.bot.channels[500]
    run(play.play_command(sessions.GAMES).callback(ctx, game, pace, start=start))
    return ctx


def press(action, user=SCOTT, session_id=1, manager=False):
    interaction = Interaction(user, Guild(111))
    interaction.user.guild_permissions = types.SimpleNamespace(manage_guild=manager)
    run(sessions.pressed(interaction, session_id, action))
    return interaction


def move(value, user, session_id=1):
    """Press ✍️ Your move, then answer what it asks."""
    interaction = Interaction(user, Guild(111))
    run(sessions.ask(interaction, session_id))
    if interaction.modal is None and not (interaction.sent and interaction.last.view):
        return interaction  # Nothing to do (a refusal)
    step = sessions.get(session_id).step
    answer = Interaction(user, Guild(111))
    run(sessions.answered(answer, session_id, step, value))
    return answer


def board(bot):
    session = sessions.get(1)
    return channel(bot).messages[session.message_id]


def last_post(bot):
    """The last thing the game said (the board, moved down after it, has no text)."""
    return next(m for m in reversed(channel(bot).sent) if m.content)


# --- The lobby ---
def test_a_lobby_is_one_message_edited_as_people_join(bot):
    ctx = open_lobby()
    lobby = ctx.last
    assert lobby.embed.title == "🔤 Words: join in" and "**Players (1/4, 2 needed):** <@1>" in lobby.embed.description
    assert [item.custom_id for item in lobby.view.children] == [
        f"game:1:{a}" for a in ("join", "leave", "start", "pace", "pings", "cancel")]
    joined = press("join", DAVE)
    assert "<@1> <@2>" in joined.last.embed.description  # The same message, edited in place
    assert "already in" in press("join", DAVE).last.content
    assert sessions.get(1).players == [SCOTT.id, DAVE.id]


def test_only_one_game_per_channel():
    open_lobby()
    ctx = open_lobby(DAVE)
    assert "already a game" in ctx.last.content and ctx.last.private


def test_starting_needs_the_host_and_enough_players(bot):
    open_lobby()
    assert "needs 2 players" in press("start").last.content
    press("join", DAVE)
    assert "Only the host" in press("start", DAVE).last.content
    press("start")
    session = sessions.get(1)
    assert session.phase == "playing" and session.step == "word:0"
    assert session.deadline == NOON + timedelta(seconds=30)  # Live: seconds
    assert "Words has started" in last_post(bot).content or any(
        "Words has started" in (m.content or "") for m in channel(bot).sent)
    assert [item.custom_id.split(":")[2] for item in board(bot).view.children] == [
        "card", "move", "join", "pings", "cancel"]


def test_the_host_leaving_hands_it_on_and_a_full_lobby_is_full():
    open_lobby()
    for user in (DAVE, PAT, AMY):
        press("join", user)
    assert "It's full" in press("join", User(5, "bob")).last.content
    press("leave", SCOTT)
    assert sessions.get(1).host_id == DAVE.id


def test_cancelling(bot):
    open_lobby()
    assert "Only the host" in press("cancel", DAVE).last.content
    assert press("cancel", DAVE, manager=True).last.content == "Cancelled."  # Manage Server can
    assert sessions.get(1).phase == "cancelled" and "cancelled" in board(bot).embed.description


# --- Playing ---
def started(pace="live", players=(SCOTT, DAVE)):
    open_lobby(pace=pace)
    for user in players[1:]:
        press("join", user)
    press("start")


def test_cards_are_private_and_only_for_players():
    started()
    card = press("card", DAVE)
    assert card.last.private and card.last.embed.title == "Your card, 2"
    assert "not in this one" in press("card", PAT).last.content


def test_moves_go_in_turn_and_the_reveal_comes_at_the_end(bot):
    started()
    assert move("hello", DAVE).last.content == "Not your turn."
    assert "One word" in move("two words", SCOTT).last.content and sessions.get(1).step == "word:0"
    assert move("hello", SCOTT).last.content == "Thanks."
    assert sessions.get(1).step == "word:1"
    move("there", DAVE)
    session = sessions.get(1)
    assert session.phase == "done"
    reveal = channel(bot).sent[-1]
    assert reveal.embed.title == "The words" and reveal.embed.description == "hello there"
    assert [item.custom_id for item in reveal.view.children] == ["game:1:again"]
    assert db.conn.execute("SELECT user_id, points, won, role FROM game_results ORDER BY user_id").fetchall() == [
        (1, 1, 1, "talker"), (2, 1, 1, "talker")]  # Kept for all-time tables, though nothing shows them yet


def test_an_answer_to_a_step_thats_gone_is_too_late():
    started()
    step = sessions.get(1).step
    move("hello", SCOTT)
    late = Interaction(SCOTT, Guild(111))
    run(sessions.answered(late, 1, step, "again"))
    assert late.last.content == "Too late: the game's moved on."


def test_time_running_out_moves_it_on(game, bot):
    started()
    game.set(NOON + timedelta(seconds=31), sessions)
    run(sessions.tick(sessions.now()))
    assert sessions.get(1).step == "word:1" and any(m.content == "Too slow." for m in channel(bot).sent)


def test_play_again_keeps_everyone(bot):
    started()
    move("a", SCOTT)
    move("b", DAVE)
    press("again", DAVE, session_id=1)
    again = sessions.get(2)
    assert again.phase == "lobby" and again.host_id == DAVE.id and set(again.players) == {SCOTT.id, DAVE.id}


def test_a_game_that_wont_move_on_is_ended(game, monkeypatch):
    started()
    monkeypatch.setattr(Words, "timeout", lambda self, session: [])  # A bug: time's up, nothing changes
    game.set(NOON + timedelta(seconds=31), sessions)
    run(sessions.tick(sessions.now()))
    assert sessions.get(1).phase == "expired"


def test_a_game_survives_a_restart(game, bot):
    """Everything's in the database, and the buttons are read back from their ids: a fresh start carries on."""
    started()
    sessions._locks.clear()  # What a restart forgets
    move("hello", SCOTT)
    assert sessions.get(1).step == "word:1"
    item = sessions.GameButton(1, "move")
    match = sessions.GameButton.__discord_ui_compiled_template__.fullmatch(item.custom_id)
    assert run(sessions.GameButton.from_custom_id(None, item.item, match)).action == "move"


# --- Through the day ---
def test_async_moves_have_hours_and_a_nudge(game, bot):
    started(pace="async")
    session = sessions.get(1)
    assert session.deadline == NOON + timedelta(hours=4) and session.nudge_at == NOON + timedelta(hours=3)
    notice = next(m for m in channel(bot).sent if (m.content or "").startswith("⏳"))
    assert "<@1>" in notice.content and notice.allowed_mentions is sessions.NO_PINGS  # Named, not pinged
    game.set(NOON + timedelta(hours=3, seconds=1), sessions)
    run(sessions.tick(sessions.now()))
    assert last_post(bot).content.startswith("⏰ <@1>: still your move")
    assert channel(bot).sent[-1] is board(bot)  # And the board's moved down under it


def test_the_clock_stops_overnight():
    """23:00-07:00 in London doesn't count: 4 hours from 21:00 is 09:00 the next day."""
    nine_pm = datetime(2026, 10, 26, 21, 0, tzinfo=timezone.utc)  # 21:00 GMT
    assert sessions.after(nine_pm, 4 * 3600, "async") == datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)
    assert sessions.after(nine_pm, 4 * 3600, "live") == nine_pm + timedelta(hours=4)
    midnight = datetime(2026, 10, 27, 0, 30, tzinfo=timezone.utc)  # In the quiet: it starts at 07:00
    assert sessions.after(midnight, 3600, "async") == datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)
    summer = datetime(2026, 7, 1, 20, 0, tzinfo=timezone.utc)  # 21:00 BST
    assert sessions.after(summer, 4 * 3600, "async") == datetime(2026, 7, 2, 8, 0, tzinfo=timezone.utc)  # 09:00 BST


def test_pings_only_for_those_who_asked(bot):
    assert press("pings", DAVE).last.content.startswith("🔔")
    started(pace="async")
    move("hello", SCOTT)  # Dave's turn now: he asked, so he's pinged
    notice = last_post(bot)
    assert notice.content.startswith("⏳ <@2>") and [u.id for u in notice.allowed_mentions.users] == [DAVE.id]
    assert press("pings", DAVE).last.content.startswith("🔕") and not sessions.pings_on(DAVE.id)


def test_joining_mid_game_deals_you_in_next_round(bot):
    started()
    joined = press("join", PAT)
    assert "next round" in joined.last.content and joined.last.private
    assert sessions.get(1).players == [SCOTT.id, DAVE.id]  # Not this round
    assert "**Next round:** <@3>" in board(bot).embed.description
    assert "already" in press("join", PAT).last.content and "this round already" in press("join", DAVE).last.content
    assert next(item.item.label for item in board(bot).view.children if item.action == "join") == "Join next round"
    move("a", SCOTT)
    move("b", DAVE)
    assert "<@3>" in channel(bot).sent[-1].content  # The reveal says who's waiting
    press("again", SCOTT)
    assert sessions.get(2).players == [SCOTT.id, DAVE.id, PAT.id]


def test_the_next_round_cant_be_overfull():
    started(players=(SCOTT, DAVE, PAT))
    press("join", AMY)  # Four is the most
    assert "full" in press("join", User(5, "bob")).last.content


def test_the_board_moves_down_after_the_games_posts(bot):
    started()
    first = board(bot)
    move("hello", SCOTT)
    assert channel(bot).sent[-1] is board(bot) and board(bot) is not first
    assert getattr(first, "deleted", False)  # The old one's gone, so there's one board


def test_the_board_moves_down_when_chat_buries_it(game, bot):
    started()
    buried = board(bot)

    def chat(n, author=DAVE):
        for _ in range(n):
            run(sessions.chatted(types.SimpleNamespace(guild=Guild(111), author=author, channel=channel(bot))))

    game.set(NOON + timedelta(seconds=40), sessions)  # Past BUMP_GAP since the last move
    chat(sessions.BUMP_AFTER - 1)
    assert board(bot) is buried
    chat(1)
    assert board(bot) is not buried and channel(bot).sent[-1] is board(bot)
    moved = board(bot)
    chat(sessions.BUMP_AFTER)  # Again straight away: not yet (BUMP_GAP)
    assert board(bot) is moved
    game.set(NOON + timedelta(seconds=80), sessions)
    chat(1)
    assert board(bot) is not moved


def test_chat_with_no_game_on_moves_nothing(bot):
    for _ in range(sessions.BUMP_AFTER + 1):
        run(sessions.chatted(types.SimpleNamespace(guild=Guild(111), author=DAVE, channel=channel(bot))))
    assert channel(bot).sent == []


def test_live_games_dont_post_turn_notices_unless_someones_pinged(bot):
    started()
    assert not any((m.content or "").startswith("⏳") for m in channel(bot).sent)


def test_an_async_game_can_start_itself(game, bot):
    open_lobby(pace="async", start="1pm")
    session = sessions.get(1)
    assert session.starts_at == datetime(2026, 10, 26, 13, 0, tzinfo=timezone.utc)
    press("join", DAVE)
    game.set(datetime(2026, 10, 26, 13, 0, 5, tzinfo=timezone.utc), sessions)
    run(sessions.tick(sessions.now()))
    assert sessions.get(1).phase == "playing"


def test_a_lobby_nobody_starts_goes(game, bot):
    open_lobby()
    game.set(NOON + timedelta(minutes=16), sessions)
    run(sessions.tick(sessions.now()))
    assert sessions.get(1).phase == "expired"


def test_a_start_time_is_only_for_async():
    ctx = open_lobby(start="9am")
    assert "through the day" in ctx.last.content and sessions.get(1) is None


@pytest.mark.parametrize("pace", ["live", "async"])
def test_start_now_opens_the_lobby_for_the_host_to_start(pace):
    open_lobby(pace=pace, start=" Right  NOW ")
    session = sessions.get(1)
    assert session.phase == "lobby" and session.pace == pace and session.starts_at is None


def test_no_network_is_tried_again(game, monkeypatch):
    started()

    async def no_network(session, moment):
        raise OSError("Temporary failure in name resolution")
    monkeypatch.setattr(sessions, "due", no_network)
    game.set(NOON + timedelta(seconds=31), sessions)
    run(sessions.tick(sessions.now()))
    assert sessions.get(1).phase == "playing"  # Not ended: it'll be due again next time round
