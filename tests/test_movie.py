"""Movie night: /nowplaying, /shhh, /nowplaying rate, /nowplaying predict and /nowplaying bingo (ktdi.features.movie)."""

import types
from datetime import datetime, timedelta, timezone

import discord
import pytest

from ktdi import db
from ktdi.features import fun, movie
from tests.fakes import Channel, Ctx, Guild, User, run

SCOTT, DAVE, PAT, AMY = User(1, "scott"), User(2, "dave"), User(3, "pat"), User(4, "amy")
EIGHT_PM = datetime(2026, 10, 3, 19, 0, tzinfo=timezone.utc)


@pytest.fixture
def at(clock):
    """at(minutes) sets the clock to that many minutes after 8pm."""
    def set_time(minutes):
        clock.set(EIGHT_PM + timedelta(minutes=minutes), movie)
    set_time(0)
    return set_time


def live(minutes):
    """The live Discord timestamp for that many minutes after 8pm."""
    return f"<t:{int((EIGHT_PM + timedelta(minutes=minutes)).timestamp())}:R>"


def np(command, user=SCOTT, **kwargs):
    ctx = Ctx(user)
    run(getattr(movie, f"np_{command}").callback(ctx, **kwargs))
    return ctx.last


def test_set_doesnt_start_it(at, bot):
    reply = np("set", title="  Shrek 2 ")
    assert reply.content.startswith("🎬 **Up next:** Shrek 2") and "`/nowplaying start`" in reply.content
    assert bot.activity is None
    assert np("show").content.startswith("🎬 **Up next:** Shrek 2")
    np("set", title="Shrek")  # changed our minds before starting
    assert movie.current_movie(111).title == "Shrek"


def test_start_pause_resume_end(at, bot):
    assert "Nothing's lined up" in np("start").content
    np("set", title="Shrek 2")
    at(5)
    reply = np("start")
    assert reply.content.startswith("# ▶️ GO!\n🎬 **Starting: Shrek 2.** Phones down, lights off.\n"
                                    f"-# ⏱️ Started {live(5)}. `/nowplaying pause`")
    assert bot.activity.type == discord.ActivityType.watching and bot.activity.name == "Shrek 2"
    assert "already started" in np("start").content

    at(52)
    reply = np("pause", reason="snacks\nand drinks")
    assert reply.content == ("⏸️ **Paused** Shrek 2 at 0:47:00.\n> snacks and drinks\n"
                             f"-# Paused {live(52)}. `/nowplaying resume` to carry on.")
    assert bot.activity.name == "Shrek 2 (paused)"
    assert "already paused" in np("pause").content
    at(60)
    assert np("show").content.startswith("⏸️ **Paused:** Shrek 2 at 0:47:00")  # the clock stops while paused

    at(64)
    reply = np("resume")
    assert reply.content.startswith("▶️ **Resumed** Shrek 2 at 0:47:00, after 12m.")
    assert any(line in reply.content for line in movie.LONG_PAUSE_LINES)
    # The live clock starts 12 minutes later than the film did, so it shows time watched, not counting the pause.
    assert reply.content.endswith(f"\n-# ⏱️ Started {live(5 + 12)}, not counting pauses.")
    assert "It's not paused" in np("resume").content
    at(70)
    assert np("show").content == ("▶️ **Now playing:** Shrek 2\n"
                                  f"-# ⏱️ Started {live(17)}, not counting pauses. Put on by <@1>.")
    assert "still on" in np("set", title="Something else").content

    at(158)  # 153 minutes since the start, 12 of them paused
    reply = np("end")
    assert reply.content.startswith("🎬 **That's Shrek 2 done.** 2h 21m watched, plus 12m paused.")
    assert "/nowplaying rate" in reply.content and bot.activity is None
    assert movie.current_movie(111) is None
    assert "Nothing's lined up" in np("show").content


def test_short_pauses_get_no_comment(at):
    np("set", title="Up")
    np("start")
    np("pause")
    at(3)
    assert np("resume").content == ("▶️ **Resumed** Up at 0:00:00, after 3m.\n"
                                    f"-# ⏱️ Started {live(3)}, not counting pauses.")


def test_elapsed_for_catching_up(at, sleeps):
    assert "`/nowplaying set <title>` first" in np("elapsed").content
    np("set", title="Shrek 2")
    assert "`/nowplaying start` it first" in np("elapsed").content
    at(5)
    np("start")
    at(52.5)  # 47m 30s in
    reply = np("elapsed")
    now = int((EIGHT_PM + timedelta(minutes=52.5)).timestamp())
    assert reply.original == (f"⏱️ **Shrek 2** is at **0:47:30** (as of <t:{now}:T>).\n"
                              f"To catch up: skip to **0:47:40**, pause, and press play <t:{now + 10}:R>.")
    assert reply.private  # only for the person catching up
    # When the moment comes, the countdown is replaced rather than left saying "press play 8 seconds ago".
    assert sleeps.delays[-1] == 10  # (after the start's countdown)
    assert reply.edits == ["▶️ **Shrek 2**: you should be at **0:47:40** and back in sync."]

    np("pause")
    at(60)  # the film doesn't move while paused
    assert np("elapsed").content.startswith("⏸️ **Shrek 2** is paused at **0:47:30**.")


def test_elapsed_lines_up_on_a_whole_second(clock, sleeps):
    np("set", title="Up")
    clock.set(EIGHT_PM, movie)
    np("start")
    clock.set(EIGHT_PM + timedelta(seconds=61.25), movie)  # 1:01.25 in
    reply = np("elapsed").original
    # Press play at the next whole second plus 10 (1:12 into the film), not 10.0 seconds from a quarter past.
    sync_at = int(EIGHT_PM.timestamp()) + 72
    assert "is at **0:01:01**" in reply and f"skip to **0:01:12**, pause, and press play <t:{sync_at}:R>" in reply


@pytest.mark.parametrize("typed, seconds", [
    ("1:07:30", 4050), ("47:30", 2850), ("0:00:05", 5), ("1h 7m 30s", 4050), ("1h7m", 4020), ("47m", 2820),
    ("47 mins", 2820), ("2 hours", 7200), ("90s", 90), ("47", 2820), ("1hr 5min", 3900),
])
def test_parse_timecode(typed, seconds):
    assert movie.parse_timecode(typed) == seconds


@pytest.mark.parametrize("typed", ["", "soon", "1:75:00", "47:99", "13h", "5 bananas", "1h and a bit"])
def test_parse_timecode_rejects(typed):
    assert movie.parse_timecode(typed) is None


def sct(position, user=SCOTT):
    ctx = Ctx(user)
    run(movie.np_sct.callback(ctx, position=position))
    return ctx.last


def test_sct_corrects_a_playing_film(at, sleeps):
    np("set", title="Alien")
    np("start")
    at(30)  # the bot thinks 30 minutes in, but we restarted it and it's really 12:00 in
    reply = sct("12:00")
    assert reply.content == (f"⏱️ **Alien** is now at **0:12:00**.\n"
                             f"-# ⏱️ Started {live(30 - 12)}. Out of sync? `/nowplaying elapsed` to catch up.")
    assert not reply.private
    assert movie.watched_seconds(movie.current_movie(111)) == 12 * 60
    at(40)
    assert "is at **0:22:00**" in np("elapsed").original  # elapsed follows the correction


def test_sct_keeps_the_pause_total(at):
    np("set", title="Alien")
    np("start")
    at(10)
    np("pause")
    at(20)
    np("resume")  # 10 minutes paused
    at(50)
    sct("1h 5m")
    assert movie.watched_seconds(movie.current_movie(111)) == 65 * 60
    assert "⏱️ Started" in np("show").content and "not counting pauses" in np("show").content
    at(60)
    reply = np("end")
    assert "1h 15m watched, plus 10m paused." in reply.content


def test_sct_while_paused(at):
    np("set", title="Alien")
    np("start")
    at(30)
    np("pause")
    at(35)
    reply = sct("25:00")
    assert reply.content.startswith("⏱️ **Alien** is now at **0:25:00**.\n-# Still paused.")
    at(45)  # still paused: doesn't move
    assert np("show").content.startswith("⏸️ **Paused:** Alien at 0:25:00")
    at(46)
    assert np("resume").content.startswith("▶️ **Resumed** Alien at 0:25:00, after 16m.")


def test_sct_starts_a_film_started_without_the_bot(at, bot):
    assert "Nothing's lined up" in sct("10:00").content
    np("set", title="Alien")
    reply = sct("10m")
    assert "is now at **0:10:00**. It's started too." in reply.content
    assert movie.watched_seconds(movie.current_movie(111)) == 600 and bot.activity.name == "Alien"


def test_sct_rejects_nonsense(at):
    np("set", title="Alien")
    np("start")
    reply = sct("soon")
    assert reply.private and "I don't understand `soon`" in reply.content


def test_timecodes():
    assert [movie.timecode(s) for s in (0, 59, 61, 3600, 4062)] == [
        "0:00:00", "0:00:59", "0:01:01", "1:00:00", "1:07:42"]


def test_ending_while_paused_counts_the_pause(at):
    np("set", title="Up")
    np("start")
    at(30)
    np("pause")
    at(40)
    assert "30m watched, plus 10m paused." in np("end").content


def test_ending_something_never_started_saves_it_for_later(at):
    np("set", title="Cats")
    run(movie.predict.callback(Ctx(DAVE), guess="regret"))
    reply = np("end").content
    assert reply == ("🍿 It never started. Cats is on the watchlist (not yet watched) with its 1 sealed prediction. "
                     "`/nowplaying set Cats` brings it back.")
    assert movie.current_movie(111) is None and movie.movie_to_rate(111) is None
    assert [m.title for m in movie.watchlist(111)] == ["Cats"]
    assert db.conn.execute("SELECT COUNT(*) FROM movie_predictions").fetchone()[0] == 1  # nothing deleted


def test_pause_needs_a_film_playing(at):
    assert "`/nowplaying set <title>` first" in np("pause").content
    np("set", title="Up")
    assert "`/nowplaying start` it first" in np("pause").content


def test_shhh(at):
    ctx = Ctx(SCOTT)
    run(movie.shhh.callback(ctx))
    reply = ctx.last
    assert reply.content.startswith("# 🤫 SHHHH\n") and any(line in reply.content for line in movie.SHHH_LINES)
    assert "Requested by <@1>." in reply.content
    assert reply.allowed_mentions.users is False and reply.allowed_mentions.everyone is False  # no pings

    np("set", title="Shrek 2")
    run(movie.shhh.callback(ctx))
    assert "Shrek 2" not in ctx.last.content  # lined up isn't playing
    np("start")
    run(movie.shhh.callback(ctx, reason="the  Holding Out\nFor A Hero bit"))
    assert "Shrek 2" in ctx.last.content and "\n> the Holding Out For A Hero bit\n" in ctx.last.content


def rate(user, score=None):
    ctx = Ctx(user)
    run(movie.rate.callback(ctx, score))
    return ctx.last


def test_rating(at):
    assert "Nothing to rate" in rate(SCOTT, 5).content
    np("set", title="Shrek 2")
    assert "Nothing to rate" in rate(SCOTT, 5).content  # not started
    np("start")
    reply = rate(SCOTT, 9)  # can rate while it's on
    assert reply.content == "⭐ <@1> gave **Shrek 2** a 9/10.\n**9.0/10** from 1 rating."
    assert reply.allowed_mentions.users is False
    np("end")
    rate(DAVE, 8)
    rate(SCOTT, 10)  # changing your mind replaces your score
    assert "**9.0/10** from 2 ratings." in rate(SCOTT).content
    assert "is wrong" not in rate(SCOTT).content
    reply = rate(PAT, 2)
    assert "<@3> gave it a 2. <@3> is wrong." in reply.content
    listing = rate(SCOTT).content
    assert "<@1>: 10/10\n<@2>: 8/10\n<@3>: 2/10" in listing

    np("set", title="Next one")  # lined up, not started: ratings still go to the last film
    rate(AMY, 6)
    assert "**Shrek 2**" in rate(AMY).content


def test_predictions_are_sealed_then_revealed_and_judged(at, bot):
    np("set", title="Shrek 2")
    ctx = Ctx(DAVE)
    run(movie.predict.callback(ctx, guess="Donkey  gets the girl"))
    public, private = ctx.sent
    assert public.content == "🔮 <@2> has made a sealed prediction about Shrek 2." and not public.private
    assert private.private and "Donkey gets the girl" in private.content
    assert "Donkey" not in public.content

    typed = Ctx(PAT, slash=False)
    run(movie.predict.callback(typed, guess="Puss steals the show"))
    assert typed.message.deleted and "sealed prediction" in typed.last.content

    np("start")
    channel = Channel(500, Guild())
    ctx = Ctx(SCOTT, channel=channel)
    run(movie.np_end.callback(ctx))
    header, first, second = channel.sent
    assert "The predictions for Shrek 2 are in" in header.content
    assert first.content == "🔮 <@2>: Donkey gets the girl" and first.reactions == ["✅", "❌"]
    assert first.allowed_mentions.users is False

    def react(handler, message, user, emoji):
        run(handler(types.SimpleNamespace(emoji=emoji, user_id=user.id, message_id=message.id)))

    react(movie.prediction_vote, first, SCOTT, "✅")
    react(movie.prediction_vote, first, AMY, "✅")
    react(movie.prediction_vote, first, DAVE, "✅")  # can't judge your own: ignored
    react(movie.prediction_vote, first, PAT, "❌")
    react(movie.prediction_vote, first, bot.user, "❌")  # the bot's own reactions: ignored
    react(movie.prediction_vote, second, SCOTT, "❌")
    assert movie.prediction_record(111, DAVE.id) == (1, 1)
    assert movie.prediction_record(111, PAT.id) == (0, 1)

    react(movie.prediction_unvote, first, SCOTT, "✅")
    react(movie.prediction_unvote, first, AMY, "✅")
    assert movie.prediction_record(111, DAVE.id) == (0, 1)  # 0 yes, 1 no now
    react(movie.prediction_vote, first, SCOTT, "✅")
    react(movie.prediction_vote, first, AMY, "✅")

    sheet = Ctx(SCOTT)
    run(fun.rapsheet.callback(sheet, DAVE))
    assert "🔮 Called it 1 time (of 1 movie prediction)." in sheet.last.content


def test_predicting_needs_a_film(at):
    ctx = Ctx(DAVE)
    run(movie.predict.callback(ctx, guess="anything"))
    assert "Nothing's lined up" in ctx.last.content and ctx.last.private


def mark(user, square):
    ctx = Ctx(user)
    run(movie.bingo_mark.callback(ctx, square))
    return ctx.last


def test_bingo_cards():
    card = movie.bingo_card(1, SCOTT.id)
    assert len(card) == 25 and len(set(card)) == 25 and card[12] == movie.BINGO_FREE_SPACE
    assert movie.bingo_card(1, SCOTT.id) == card  # the same every time
    assert movie.bingo_card(1, DAVE.id) != card and movie.bingo_card(2, SCOTT.id) != card
    assert len(movie.BINGO_LINES) == 12
    assert movie.has_bingo({1, 7, 13, 19, 25}) and movie.has_bingo({5, 9, 13, 17, 21})
    assert movie.has_bingo({11, 12, 13, 14, 15}) and movie.has_bingo({3, 8, 13, 18, 23})
    assert not movie.has_bingo({1, 2, 3, 4, 6})


def test_bingo(at):
    ctx = Ctx(SCOTT)
    run(movie.bingo_show.callback(ctx))
    assert "No film lined up" in ctx.last.content
    np("set", title="Shrek 2")
    run(movie.bingo_show.callback(ctx))
    embed = ctx.last.embed
    assert ctx.last.private and embed.title == "🎯 Your bingo card: Shrek 2"
    assert "```\n 1  2  3  4  5\n 6  7  8  9 10\n11 12  X 14 15\n" in embed.description
    assert f"`13` ~~{movie.BINGO_FREE_SPACE}~~" in embed.description
    assert len(embed) <= 6000 and len(embed.description) <= 4096

    assert "Wait for `/nowplaying start`" in mark(SCOTT, 1).content
    np("start")
    card = movie.bingo_card(movie.current_movie(111).id, SCOTT.id)
    reply = mark(SCOTT, 3)
    assert reply.content == f"🎯 <@1> marked **{card[2]}** (2/25)" and reply.allowed_mentions.users is False
    assert "already marked" in mark(SCOTT, 3).content
    assert "free space" in mark(SCOTT, 13).content
    mark(SCOTT, 8)
    mark(SCOTT, 18)
    reply = mark(SCOTT, 23)  # down the middle, through the free space
    assert "# 🎉 BINGO!" in reply.content
    reply = mark(SCOTT, 11)
    assert "BINGO" not in reply.content  # only called once per film

    unmark = Ctx(SCOTT)
    run(movie.bingo_unmark.callback(unmark, 11))
    assert "Unmarked square 11" in unmark.last.content
    run(movie.bingo_unmark.callback(unmark, 11))
    assert "isn't marked" in unmark.last.content

    run(movie.bingo_show.callback(ctx))
    assert "```\n 1  2  X  4  5\n 6  7  X  9 10\n11 12  X 14 15\n16 17  X 19 20\n21 22  X 24 25\n```" in ctx.last.embed.description
    assert "🎉 Bingo: <@1>" in np("end").content
    sheet = Ctx(DAVE)
    run(fun.rapsheet.callback(sheet, SCOTT))
    assert "🎉 Won movie bingo 1 time." in sheet.last.content


def test_bingo_by_prefix_goes_by_dm(at):
    np("set", title="Up")
    ctx = Ctx(SCOTT, slash=False)
    run(movie.bingo_show.callback(ctx))
    assert "Sent you your card" in ctx.last.content
    assert SCOTT.dms  # the card itself
    SCOTT.dms.clear()


def test_bingo_autocomplete_offers_unmarked_squares(at):
    np("set", title="Up")
    np("start")
    mark(SCOTT, 1)
    interaction = types.SimpleNamespace(guild_id=111, user=SCOTT)
    choices = run(movie.bingo_square_autocomplete(interaction, ""))
    assert [c.value for c in choices] == [n for n in range(2, 26) if n != 13]
    assert choices[0].name.startswith("2. ")
    assert [c.value for c in run(movie.bingo_square_autocomplete(interaction, "7"))] == [7]  # by number
    word = movie.bingo_card(movie.current_movie(111).id, SCOTT.id)[4].split()[-1]
    assert 5 in [c.value for c in run(movie.bingo_square_autocomplete(interaction, word.upper()))]  # or by words


def test_history(at):
    ctx = Ctx(SCOTT)
    run(movie.np_history.callback(ctx))
    assert "Nothing watched yet" in ctx.last.content
    for title, score in (("Shrek", 8), ("Shrek 2", None)):
        np("set", title=title)
        np("start")
        if score:
            rate(SCOTT, score)
        np("end")
    run(movie.np_history.callback(ctx))
    assert ctx.last.embed.description == ("**Shrek 2**: not rated, 03 Oct 2026\n"
                                          "**Shrek**: 8.0/10 (1 rating), 03 Oct 2026")


def test_changing_the_film_saves_the_old_one_to_the_watchlist(at):
    np("set", title="Shrek")
    run(movie.predict.callback(Ctx(DAVE), guess="Donkey gets the girl"))
    run(movie.predict.callback(Ctx(PAT), guess="ogres"))
    shrek = movie.current_movie(111).id
    reply = np("set", title="SHREK")  # same film, different capitals: just retyped
    assert "watchlist" not in reply.content and movie.current_movie(111).id == shrek

    reply = np("set", title="Alien")
    assert "-# SHREK is on the watchlist (not yet watched) with its 2 sealed predictions." in reply.content
    assert movie.predictions(movie.current_movie(111).id) == []  # Alien starts with none
    assert [m.title for m in movie.watchlist(111)] == ["SHREK"]

    reply = np("set", title="shrek")  # back off the watchlist, predictions and all; Alien goes on it
    assert "Back from the watchlist with 2 sealed predictions." in reply.content
    assert "Alien is on the watchlist (not yet watched)." in reply.content
    assert movie.current_movie(111).id == shrek and len(movie.predictions(shrek)) == 2
    assert [m.title for m in movie.watchlist(111)] == ["Alien"]


def test_watchlist(at):
    ctx = Ctx(SCOTT)
    run(movie.np_watchlist.callback(ctx))
    assert "The watchlist is empty" in ctx.last.content
    np("set", title="Cats")
    run(movie.predict.callback(Ctx(DAVE), guess="regret"))
    np("end")
    at(1)
    np("set", title="Jaws", user=DAVE)
    np("end")
    run(movie.np_watchlist.callback(ctx))
    assert ctx.last.embed.description == ("**Jaws**, added by <@2>\n"
                                          "**Cats**, added by <@1>, 1 sealed prediction")
    choices = run(movie.watchlist_autocomplete(types.SimpleNamespace(guild_id=111), "ca"))
    assert [(c.name, c.value) for c in choices] == [("Cats (watchlist)", "Cats")]
    assert run(movie.watchlist_autocomplete(types.SimpleNamespace(guild_id=222), "")) == []  # per server


def watchlist_cmd(command, user=SCOTT, **kwargs):
    ctx = Ctx(user)
    run(getattr(movie, f"np_watchlist_{command}").callback(ctx, **kwargs))
    return ctx.last


def test_watchlist_add_and_remove(at):
    assert watchlist_cmd("add", title="  Alien ").content == "🍿 Added **Alien** to the watchlist (1 to watch)."
    assert "already on the watchlist" in watchlist_cmd("add", title="ALIEN").content
    watchlist_cmd("add", title="Jaws", user=DAVE)
    assert [m.title for m in movie.watchlist(111)] == ["Alien", "Jaws"]
    assert watchlist_cmd("remove", title="alien").content == "🍿 Took **Alien** off the watchlist."
    assert [m.title for m in movie.watchlist(111)] == ["Jaws"]
    assert "There's no Alien on the watchlist" in watchlist_cmd("remove", title="Alien").content
    assert db.conn.execute("SELECT COUNT(*) FROM movies WHERE dropped_at IS NOT NULL").fetchone()[0] == 1  # kept
    np("set", title="Alien")  # a dropped film doesn't come back: this is a new one
    assert movie.current_movie(111).dropped_at is None


FILMS = [("Alien (1979)", "alien"), ("Halloween (1978)", "halloween-1978"), ("Halloween (2018)", "halloween-2018"),
         ("Braindead (1992)", "braindead-1992")]


@pytest.fixture
def letterboxd_list(monkeypatch):
    """/nowplaying watchlist import reads this instead of Letterboxd."""
    from ktdi.lib import letterboxd

    async def fake_fetch(url):
        if "nope" in url:
            raise letterboxd.LetterboxdError("Letterboxd says that list doesn't exist (or it's private).")
        return letterboxd.FilmList("Halloween 2026", "jenny", "https://letterboxd.com/jenny/list/halloween-2026/",
                                   [letterboxd.Film(n, f"https://letterboxd.com/film/{s}/") for n, s in FILMS])
    monkeypatch.setattr(movie.letterboxd, "fetch_list", fake_fetch)


def test_import_from_letterboxd(at, letterboxd_list):
    watchlist_cmd("add", title="Braindead (1992)", user=DAVE)
    at(1)
    reply = watchlist_cmd("import", url="https://letterboxd.com/jenny/list/halloween-2026/")
    assert reply.content == (
        "🍿 Added **3 films** from [Halloween 2026](<https://letterboxd.com/jenny/list/halloween-2026/>) by jenny "
        "to the watchlist: Alien (1979), Halloween (1978), Halloween (2018).\n"
        "-# 1 was already on it.\n-# `/nowplaying watchlist` to see them, `/nowplaying set <title>` to line one up.")
    # The list's own order, after what was there (newest first by when it was added).
    assert [m.title for m in movie.watchlist(111)] == ["Alien (1979)", "Halloween (1978)", "Halloween (2018)",
                                                       "Braindead (1992)"]
    assert "Everything on" in watchlist_cmd("import", url="https://letterboxd.com/jenny/list/halloween-2026/").content

    ctx = Ctx(SCOTT)
    run(movie.np_watchlist.callback(ctx))
    embed = ctx.last.embed
    assert embed.title == "🍿 To watch (4)"
    assert embed.description.startswith("**[Alien (1979)](<https://letterboxd.com/film/alien/>)**, added by <@1>\n")


def test_import_errors_are_shown(at, letterboxd_list):
    assert watchlist_cmd("import", url="https://letterboxd.com/jenny/list/nope/").content == (
        "🍿 Letterboxd says that list doesn't exist (or it's private).")
    assert movie.watchlist(111) == []


def test_lining_up_an_imported_film(at, letterboxd_list):
    watchlist_cmd("import", url="https://letterboxd.com/jenny/list/halloween-2026/")
    reply = np("set", title="alien")  # without the year: there's only one Alien
    assert reply.content.startswith("🎬 **Up next:** [Alien (1979)](<https://letterboxd.com/film/alien/>)")
    assert "Back from the watchlist" in reply.content
    np("set", title="Halloween")  # two Halloweens: neither is guessed, so it's a new film
    assert movie.current_movie(111).link is None
    assert len([m for m in movie.watchlist(111) if m.title.startswith("Halloween (")]) == 2
    np("set", title="Halloween (2018)")  # exact
    assert movie.current_movie(111).link == "https://letterboxd.com/film/halloween-2018/"


def test_watchlist_films_are_never_revealed_or_rated(at):
    np("set", title="Cats")
    run(movie.predict.callback(Ctx(DAVE), guess="regret"))
    np("end")
    assert "Nothing watched yet" in predictions_for().content
    assert "Nothing to rate" in rate(SCOTT, 5).content
    assert movie.prediction_record(111, DAVE.id) == (0, 0)


def test_rewatches_are_numbered_with_their_own_everything(at):
    watch("Alien", [(DAVE, "the cat survives")])
    first = movie.movie_to_rate(111)
    rate(SCOTT, 9)
    np("set", title="alien")
    assert "**Up next:** alien (watch #2)" in np("show").content
    run(movie.predict.callback(Ctx(DAVE), guess="the cat survives again"))
    assert "Starting: alien (watch #2)." in np("start").content
    second = movie.current_movie(111)
    assert (first.watch_number, second.watch_number) == (1, 2)
    assert movie.bingo_card(first.id, SCOTT.id) != movie.bingo_card(second.id, SCOTT.id)  # a new card
    assert movie.bingo_marks(second.id, SCOTT.id) == {movie.BINGO_FREE}  # nothing carried over
    assert "gave **alien (watch #2)** a 6/10.\n**6.0/10** from 1 rating." in rate(SCOTT, 6).content
    reply = np("end")
    assert reply.content.startswith("🎬 **That's alien (watch #2) done.**")

    ctx = Ctx(SCOTT)
    run(movie.np_history.callback(ctx))
    assert ctx.last.embed.description.splitlines() == [
        "**alien (watch #2)**: 6.0/10 (1 rating), 0/1 predictions called, 03 Oct 2026",
        "**Alien**: 9.0/10 (1 rating), 0/1 predictions called, 03 Oct 2026"]
    assert movie.next_watch_number(111, "ALIEN") == 3


def watch(title, guesses, votes=()):
    """Watch a film where (user, guess)s are predicted, then ✅/❌ each in turn by (voter, emoji, index)."""
    np("set", title=title)
    for user, guess in guesses:
        run(movie.predict.callback(Ctx(user), guess=guess))
    np("start")
    channel = Channel(500, Guild())
    run(movie.np_end.callback(Ctx(SCOTT, channel=channel)))
    revealed = channel.sent[1:]
    for voter, emoji, index in votes:
        run(movie.prediction_vote(types.SimpleNamespace(emoji=emoji, user_id=voter.id, message_id=revealed[index].id)))


def predictions_for(title=None):
    ctx = Ctx(SCOTT)
    run(movie.np_predictions.callback(ctx, title=title))
    return ctx.last


def test_prediction_history(at):
    assert "Nothing watched yet" in predictions_for().content
    watch("Alien", [(DAVE, "the cat survives"), (PAT, "everyone survives"), (AMY, "it's a robot")],
          [(SCOTT, "✅", 0), (AMY, "✅", 0), (SCOTT, "❌", 1), (DAVE, "✅", 2), (SCOTT, "❌", 2)])
    watch("Aliens", [(DAVE, "more aliens")])
    watch("Up", [])

    embed = predictions_for("alien").embed  # exact title beats "Aliens", whatever the capitals
    assert embed.title == "🔮 Predictions for Alien, 03 Oct 2026"
    assert embed.description == ("✅ <@2>: the cat survives (2–0)\n"
                                 "❌ <@3>: everyone survives (0–1)\n"
                                 "⚖️ <@4>: it's a robot (1–1)")
    assert embed.footer.text.startswith("1 of 3 called.")
    assert predictions_for("ens").embed.title.startswith("🔮 Predictions for Aliens")  # partial match
    assert predictions_for().embed.description == "Nobody predicted anything."  # the last one watched: Up
    assert "No finished film called “Jaws”" in predictions_for("Jaws").content

    ctx = Ctx(SCOTT)
    run(movie.np_history.callback(ctx))
    assert "**Alien**: not rated, 1/3 predictions called, 03 Oct 2026" in ctx.last.embed.description
    assert "**Up**: not rated, 03 Oct 2026" in ctx.last.embed.description


def test_predictions_for_each_watch(at):
    watch("Alien", [(DAVE, "first time")])
    watch("Alien", [(DAVE, "second time")])
    embed = predictions_for("Alien").embed  # the latest watch
    assert embed.title == "🔮 Predictions for Alien (watch #2), 03 Oct 2026" and "second time" in embed.description
    assert "first time" in predictions_for("alien #1").embed.description  # a particular watch
    assert "first time" in predictions_for("ali #1").embed.description
    assert "No finished film called “Alien #3”" in predictions_for("Alien #3").content
    choices = run(movie.watched_title_autocomplete(types.SimpleNamespace(guild_id=111), "ali"))
    assert [c.name for c in choices] == ["Alien (watch #2, 03 Oct 2026)", "Alien (watch #1, 03 Oct 2026)"]
    assert "first time" in predictions_for(choices[1].value).embed.description


def test_sealed_predictions_stay_sealed(at):
    np("set", title="Alien")
    run(movie.predict.callback(Ctx(DAVE), guess="secret"))
    np("start")
    assert "No finished film called “Alien”" in predictions_for("Alien").content  # not finished, so not listed
    assert movie.revealed_predictions(movie.current_movie(111).id) == []


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    """Countdowns (every /nowplaying start) don't really wait: the clock reads 1000.4 seconds, each sleep is recorded
    instead, and something can run mid-countdown."""
    record = types.SimpleNamespace(delays=[], during=None)

    async def fake_sleep(delay):
        record.delays.append(round(delay, 1))
        if record.during:
            await record.during()
    monkeypatch.setattr(movie.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(movie, "time", types.SimpleNamespace(time=lambda: 1000.4))
    return record


def test_start_counts_down(at, sleeps, bot):
    assert "Nothing's lined up" in np("start").content
    np("set", title="Alien")
    reply = np("start")
    # A live Discord timestamp counts down by itself: the next whole second (1001) plus 5. Only one edit, for GO.
    assert reply.edits[0].startswith("# ▶️ GO!\n🎬 **Starting: Alien.**") and len(reply.edits) == 1
    assert sleeps.delays == [5.6]  # from 1000.4 to 1006
    assert reply.original == ("# 🎬 Alien starts <t:1006:R>\n"
                              "-# Get ready to press play. This changes to GO when it's time.")
    assert movie.current_movie(111).started_at is not None and bot.activity.name == "Alien"
    assert "already started" in np("start").content
    assert not movie.counting_down
    assert movie.np_start.aliases == ["countdown"]  # !np countdown still works


def test_no_starting_twice_during_a_countdown(at, sleeps):
    np("set", title="Alien")
    others = []

    async def someone_else_tries():
        ctx = Ctx(DAVE)
        await movie.np_start.callback(ctx)
        await movie.np_sct.callback(ctx, position="10:00")
        others.extend(ctx.sent)
    sleeps.during = someone_else_tries
    reply = np("start")
    assert [o.content for o in others] == ["There's already a countdown going.",
                                          "There's a countdown going. Wait for it, then correct the time."]
    assert all(o.private for o in others)
    assert reply.content.startswith("# ▶️ GO!")


def test_countdown_called_off_if_the_film_changes(at, sleeps):
    np("set", title="Alien")

    async def change_film():
        await movie.np_set.callback(Ctx(DAVE), title="Jaws")
    sleeps.during = change_film
    reply = np("start")
    assert reply.content.startswith("🎬 Countdown called off")
    assert movie.current_movie(111).title == "Jaws" and movie.current_movie(111).started_at is None
    assert not movie.counting_down


# --- /nowplaying vote ---
HALLOWEEN = ["Alien (1979)", "Deadstream (2022)", "Braindead (1992)", "Nosferatu (2024)", "Tarantula (1955)",
             "Life (2017)"]


@pytest.fixture
def theatre(at, bot):
    """A shared channel (the poll lives there) and a watchlist to vote from."""
    channel = bot.add_channel(Channel(500, Guild()))
    for title in HALLOWEEN:
        movie.add_to_watchlist(111, title, SCOTT.id)
    return channel


def vote(user=SCOTT, channel=None, **kwargs):
    ctx = Ctx(user, channel=channel)
    run(movie.np_vote.callback(ctx, **kwargs))
    return ctx.last


def end_vote(channel, user=DAVE):
    ctx = Ctx(user, channel=channel)
    run(movie.np_vote_end.callback(ctx))
    return ctx.last


def cast(poll_message, **votes_by_title):
    for answer in poll_message.poll.answers:
        answer._vote_count = votes_by_title.get(answer.text, 0)


def test_vote_picks_random_films_from_the_watchlist(theatre):
    reply = vote(channel=theatre)
    poll = reply.poll
    # Open until someone ends it: as long as Discord allows (32 days).
    assert poll.question == "🍿 What are we watching next?" and poll.duration.total_seconds() == 32 * 24 * 3600
    assert len(poll.answers) == 5 and {a.text for a in poll.answers} <= set(HALLOWEEN)
    assert reply.content.startswith("-# Voting closes when someone runs `/nowplaying vote end`. The winner gets lined up.")
    assert "There's already a vote going" in vote(channel=theatre).content


def test_vote_on_chosen_films_then_end_it(theatre):
    reply = vote(channel=theatre, hours=3, films="alien, braindead (1992),  Deadstream")
    assert [a.text for a in reply.poll.answers] == ["Alien (1979)", "Braindead (1992)", "Deadstream (2022)"]
    assert reply.poll.duration.total_seconds() == 3 * 3600
    assert reply.content.startswith("-# Voting closes in 3 hours, or when someone runs `/nowplaying vote end`.")
    cast(reply, **{"Alien (1979)": 1, "Braindead (1992)": 3})
    result = end_vote(theatre)
    assert result.content.startswith("🗳️ **Braindead (1992)** wins with 3 votes.\n🎬 **Up next:** Braindead (1992)")
    assert result.content.endswith("-# Braindead (1992): 3 · Alien (1979): 1 · Deadstream (2022): 0")
    assert reply.poll.is_finalised()  # the poll was closed in Discord too
    assert movie.current_movie(111).title == "Braindead (1992)"
    assert "There's no vote going" in end_vote(theatre).content
    assert "Braindead (1992)" not in [m.title for m in movie.watchlist(111)]


def test_vote_refusals(theatre):
    assert "Not on the watchlist: Jaws" in vote(channel=theatre, films="Alien, Jaws").content
    assert "at least two films" in vote(channel=theatre, films="Alien, alien (1979)").content  # the same film twice
    assert "There's no vote going" in end_vote(theatre).content


def test_vote_needs_two_films_on_the_watchlist(at, bot):
    movie.add_to_watchlist(111, "Alien", SCOTT.id)
    assert "at least two films" in vote().content


def test_ties_and_no_votes(theatre, monkeypatch):
    reply = vote(channel=theatre, films="Alien, Life")
    assert end_vote(theatre).content == "🗳️ Voting's closed, but nobody voted. Still undecided."
    assert movie.current_movie(111) is None
    reply = vote(channel=theatre, films="Alien, Life, Tarantula")
    cast(reply, **{"Alien (1979)": 2, "Life (2017)": 2, "Tarantula (1955)": 1})
    monkeypatch.setattr(movie.random, "choice", lambda options: options[-1])  # the coin lands on Life
    assert end_vote(theatre).content.startswith("🗳️ **Life (2017)** wins with 2 votes (a 2-way tie, settled by coin toss).")


def test_the_winner_waits_if_something_is_playing(theatre):
    np("set", title="Jaws")
    np("start")
    reply = vote(channel=theatre, films="Alien, Life")
    cast(reply, **{"Alien (1979)": 1})
    assert "-# Jaws is still on: `/nowplaying set Alien (1979)` when it's done." in end_vote(theatre).content
    assert movie.current_movie(111).title == "Jaws"


def test_the_winner_swaps_out_whatever_was_lined_up(theatre):
    np("set", title="Jaws")
    reply = vote(channel=theatre, films="Alien, Life")
    cast(reply, **{"Life (2017)": 1})
    result = end_vote(theatre).content
    assert "**Up next:** Life (2017)" in result and "Jaws is on the watchlist" in result


def test_vote_closes_by_itself_when_time_runs_out(theatre):
    reply = vote(channel=theatre, films="Alien, Life")
    cast(reply, **{"Alien (1979)": 2})
    reply.poll._finalized = True
    results = types.SimpleNamespace(type=discord.MessageType.poll_result, channel=theatre,
                                    reference=types.SimpleNamespace(message_id=reply.id))
    run(movie.vote_closed_by_itself(results))
    assert theatre.sent[-1].content.startswith("🗳️ **Alien (1979)** wins with 2 votes.\n🎬 **Up next:** Alien (1979)")
    run(movie.vote_closed_by_itself(results))  # already closed: nothing more
    assert len([m for m in theatre.sent if m.content and m.content.startswith("🗳️")]) == 1
    other = types.SimpleNamespace(type=discord.MessageType.default, channel=theatre, reference=None)
    run(movie.vote_closed_by_itself(other))  # ordinary messages are ignored


def test_poll_answers_fit_discord():
    assert movie.answer_text("x" * 80) == "x" * 54 + "…" and len(movie.answer_text("x" * 80)) == 55
    assert movie.answer_text("Alien (1979)") == "Alien (1979)"


# --- Striking films off the watchlist ---
def test_strike_and_unstrike(theatre):
    reply = watchlist_cmd("strike", title="alien")
    assert reply.content.startswith("🍿 ~~Alien (1979)~~ struck off as watched.") and reply.content.endswith("5 to watch.")
    assert "already struck off" in watchlist_cmd("strike", title="Alien").content
    assert "There's no Jaws on the watchlist" in watchlist_cmd("strike", title="Jaws").content

    ctx = Ctx(SCOTT)
    run(movie.np_watchlist.callback(ctx))
    embed = ctx.last.embed
    assert embed.title == "🍿 To watch (5)"
    assert embed.description.splitlines()[-1] == "~~Alien (1979)~~ (watched 03 Oct)"  # still listed, crossed out, last
    assert embed.footer.text.startswith("1 struck off as watched.")

    choices = run(movie.unstruck_autocomplete(types.SimpleNamespace(guild_id=111), "a"))
    assert "Alien (1979)" not in [c.value for c in choices]
    assert [c.name for c in run(movie.struck_autocomplete(types.SimpleNamespace(guild_id=111), ""))] == [
        "Alien (1979) (watched)"]

    assert watchlist_cmd("unstrike", title="Alien").content == "🍿 **Alien (1979)** is back on the watchlist. 6 to watch."
    assert "isn't struck off" in watchlist_cmd("unstrike", title="Alien").content


def test_votes_leave_out_struck_films_unless_asked(theatre):
    for title in HALLOWEEN[:4]:
        watchlist_cmd("strike", title=title)
    left = set(HALLOWEEN[4:])
    reply = vote(channel=theatre, count=10)
    assert {a.text for a in reply.poll.answers} == left  # only the two not struck off
    end_vote(theatre)
    reply = vote(channel=theatre, count=10, include_watched=True)
    assert {a.text for a in reply.poll.answers} == set(HALLOWEEN)
    end_vote(theatre)
    reply = vote(channel=theatre, films="Alien, Life")  # named films are always allowed
    assert [a.text for a in reply.poll.answers] == ["Alien (1979)", "Life (2017)"]


def test_vote_hints_at_include_watched(theatre):
    for title in HALLOWEEN[:5]:
        watchlist_cmd("strike", title=title)
    assert "add `include_watched:True`" in vote(channel=theatre).content


def test_lining_up_a_struck_film(theatre):
    watchlist_cmd("strike", title="Alien")
    assert "Back from the watchlist" in np("set", title="Alien").content  # watching it again is fine


def struck_titles(guild_id=111):
    return [m.title for m in movie.watchlist(guild_id) if m.struck_at]


def test_watching_a_film_from_the_watchlist_strikes_it(theatre):
    np("set", title="Alien")
    np("start")
    rate(SCOTT, 9)
    reply = np("end")
    assert reply.content.endswith("\n-# Struck off the watchlist.")
    assert struck_titles() == ["Alien (1979)"]
    assert movie.to_watch_count(111) == 5
    entry = next(m for m in movie.watchlist(111) if m.title == "Alien (1979)")
    assert entry.started_at is None and entry.ended_at is None  # a fresh entry: the watch keeps its own row
    assert movie.movie_to_rate(111).title == "Alien (1979)" and movie.movie_to_rate(111).id != entry.id
    assert "**9.0/10** from 1 rating" in rate(SCOTT).content  # the rating stayed with the watch


def test_films_not_from_the_watchlist_stay_off_it(theatre):
    np("set", title="Jaws")
    np("start")
    assert "Struck off" not in np("end").content
    assert "Jaws" not in [m.title for m in movie.watchlist(111)]


def test_rewatching_keeps_one_struck_entry(theatre):
    for _ in range(2):
        np("set", title="Alien")  # the second time, it's the struck entry being lined up again
        np("start")
        np("end")
    assert struck_titles() == ["Alien (1979)"]
    assert movie.movie_to_rate(111).watch_number == 2


def test_readding_a_watched_film_then_watching_it(theatre):
    np("set", title="Alien")
    np("start")
    movie.add_to_watchlist(111, "Life (2017)", SCOTT.id)  # already there: nothing new
    np("end")
    watchlist_cmd("unstrike", title="Alien")
    np("set", title="Alien")
    np("start")
    np("end")
    assert struck_titles() == ["Alien (1979)"]


def test_the_vote_winner_is_struck_once_watched(theatre):
    reply = vote(channel=theatre, films="Alien, Life")
    cast(reply, **{"Life (2017)": 2})
    end_vote(theatre)
    np("start")
    np("end")
    assert struck_titles() == ["Life (2017)"]


def test_a_swapped_out_film_goes_back_unstruck(theatre):
    np("set", title="Alien")
    np("set", title="Life")  # Alien back on the watchlist, not watched
    assert struck_titles() == [] and movie.to_watch_count(111) == 5


# --- Adding by Letterboxd link ---
@pytest.fixture
def letterboxd_films(monkeypatch):
    from ktdi.lib import letterboxd
    films = {"https://letterboxd.com/film/nosferatu/": "Nosferatu (1922)",
             "https://letterboxd.com/film/nosferatu-2024/": "Nosferatu (2024)"}

    async def fake_fetch_film(url):
        link = letterboxd.check_film_url(url)
        if link not in films:
            raise letterboxd.LetterboxdError("Letterboxd says that film doesn't exist.")
        return letterboxd.Film(films[link], link)
    monkeypatch.setattr(movie.letterboxd, "fetch_film", fake_fetch_film)


NOSFERATU = "https://letterboxd.com/film/nosferatu/"


def test_add_by_link(at, letterboxd_films):
    reply = watchlist_cmd("add", link=NOSFERATU)
    assert reply.content == f"🍿 Added **[Nosferatu (1922)](<{NOSFERATU}>)** to the watchlist (1 to watch)."
    assert "already on the watchlist" in watchlist_cmd("add", link="letterboxd.com/film/nosferatu").content
    assert "doesn't exist" in watchlist_cmd("add", link="https://letterboxd.com/film/nope/").content
    assert "isn't a Letterboxd film" in watchlist_cmd("add", link="https://example.com/film/x/").content


def test_link_merges_into_a_title_only_entry(at, letterboxd_films):
    watchlist_cmd("add", title="Nosferatu")
    movie.add_to_watchlist(111, "Nosferatu (2024)", SCOTT.id, "https://letterboxd.com/film/nosferatu-2024/")
    reply = watchlist_cmd("add", title="Nosferatu", link=NOSFERATU)
    assert reply.content == f"🍿 Linked **[Nosferatu (1922)](<{NOSFERATU}>)** on the watchlist to its Letterboxd page."
    titles = sorted((m.title, m.link) for m in movie.watchlist(111))
    assert titles == [("Nosferatu (1922)", NOSFERATU), ("Nosferatu (2024)", "https://letterboxd.com/film/nosferatu-2024/")]


def test_add_with_a_link_typed_in_with_the_title(at, letterboxd_films):
    watchlist_cmd("add", title="nosferatu")
    # Typed with !, everything arrives as one string, in either order.
    assert "Linked" in watchlist_cmd("add", title=f"Nosferatu {NOSFERATU}").content
    assert len(movie.watchlist(111)) == 1
    reply = watchlist_cmd("add", title="https://letterboxd.com/film/nosferatu-2024/")
    assert "Added **[Nosferatu (2024)]" in reply.content
    assert "One link at a time" in watchlist_cmd("add", title=f"{NOSFERATU} {NOSFERATU}").content
    assert "Add what?" in watchlist_cmd("add").content
    assert watchlist_cmd("add", title="The", link="Thing").content.startswith("🍿 Added **The Thing**")
