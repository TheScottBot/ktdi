"""Campaign reminders: setting, 🔔 subscriptions, the loop, warnings, reschedule and skip, with the clock frozen."""

import types
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from ktdi import db
from ktdi.features import campaigns as c
from ktdi.lib import reminders
from tests.fakes import Channel, Ctx, User, run

UK = ZoneInfo("Europe/London")
SCOTT, DAVE, PAT, MOD = User(1, "scott"), User(2, "dave"), User(3, "pat"), User(4, "mod", mod=True)
MONDAY_NOON = datetime(2026, 9, 28, 11, 0, tzinfo=timezone.utc)  # Mon 28 Sep, 12:00 UK


@pytest.fixture
def game(clock, bot):
    """A campaign called "Game" with a channel for reminders, and the clock frozen at Monday noon."""
    clock.set(MONDAY_NOON, c)
    bot.add_channel(Channel(500))
    run(c.campaign_add.callback(Ctx(SCOTT), "Game", "https://www.dndbeyond.com/campaigns/1", None))
    return clock


def remind(when, author=SCOTT):
    ctx = Ctx(author)
    run(c.campaign_remind.callback(ctx, "Game", when=when))
    return ctx.last


def reschedule(change, author=SCOTT):
    ctx = Ctx(author)
    run(c.campaign_reschedule.callback(ctx, "Game", change=change))
    return ctx.last


def current():
    return c.get_reminder(111, "Game")


def sessions(count=3):
    """The next few start times, as 'Mon 19 Oct 19:00'."""
    reminder = current()
    anchor = date.fromisoformat(reminder.anchor)
    t, out = reminder.next_game_at, []
    for _ in range(count):
        out.append(t.astimezone(UK).strftime("%a %d %b %H:%M"))
        t = reminders.next_occurrence(reminder.schedule, t, UK, anchor)
    return out


def local(moment):
    return moment.astimezone(UK).strftime("%a %d %b %H:%M")


def react(add, message_id, user_id, emoji="🔔"):
    payload = types.SimpleNamespace(emoji=emoji, user_id=user_id, message_id=message_id)
    run((c.reminder_subscribe if add else c.reminder_unsubscribe)(payload))


def test_remind_posts_setup_message_with_bell(game):
    message = remind("mondays at 1900, 15 minutes before")
    assert "Mondays at 19:00" in message.embed.description and "pings 15 minutes before" in message.embed.description
    assert message.reactions == ["🔔"]
    assert local(current().next_run_at) == "Mon 28 Sep 18:45"


def test_bad_schedule_and_missing_campaign(game):
    assert "Add a time" in remind("mondays").content
    ctx = Ctx(SCOTT)
    run(c.campaign_remind.callback(ctx, "Nope", when="friday 7pm"))
    assert "There's no campaign" in ctx.last.content


def test_subscribing_with_the_bell(game, bot):
    message_id = remind("mondays at 1900").id
    react(True, message_id, DAVE.id)
    react(True, message_id, PAT.id)
    react(True, message_id, SCOTT.id, emoji="😂")  # wrong emoji
    react(True, message_id, bot.user.id)  # the bot's own 🔔
    react(True, 12345, SCOTT.id)  # some other message
    assert c.subscribers(current().id) == [DAVE.id, PAT.id]
    react(False, message_id, PAT.id)
    assert c.subscribers(current().id) == [DAVE.id]


def test_loop_pings_subscribers_once_then_moves_on(game, bot):
    react(True, remind("mondays at 1900, 15 minutes before").id, DAVE.id)
    due = current().next_run_at
    game.set(due - timedelta(minutes=1))
    run(c.reminder_loop.coro())
    assert bot.channels[500].sent == []  # not early

    game.set(due + timedelta(seconds=20))
    run(c.reminder_loop.coro())
    sent = bot.channels[500].sent[-1]
    assert sent.content.startswith("⏰ **Game** starts <t:") and "<@2>" in sent.content
    assert [u.id for u in sent.allowed_mentions.users] == [DAVE.id] and sent.allowed_mentions.everyone is False
    assert [b.label for b in sent.view.children] == ["D&D Beyond"]
    assert local(current().next_run_at) == "Mon 05 Oct 18:45"

    game.set(due + timedelta(seconds=50))
    run(c.reminder_loop.coro())
    assert len(bot.channels[500].sent) == 1  # never twice


def test_loop_skips_reminders_over_an_hour_late(game, bot):
    remind("mondays at 1900")
    game.set(current().next_run_at + timedelta(hours=3))
    run(c.reminder_loop.coro())
    assert bot.channels[500].sent == []
    assert local(current().next_run_at) == "Mon 05 Oct 19:00"


def test_start_date_and_fortnightly_skip(game):
    remind("every other monday at 7pm from 19 oct")
    assert sessions() == ["Mon 19 Oct 19:00", "Mon 02 Nov 19:00", "Mon 16 Nov 19:00"]
    run(c.campaign_skip.callback(Ctx(SCOTT), alias="Game"))
    # Skipping shifts a fortnightly cadence a week, across the clocks going back on 25 Oct.
    assert sessions() == ["Mon 26 Oct 19:00", "Mon 09 Nov 19:00", "Mon 23 Nov 19:00"]


def test_a_skip_pings_everyone_with_a_bell_but_the_skipper(game, bot):
    message_id = remind("mondays at 1900").id
    for user in (DAVE, PAT, SCOTT):
        react(True, message_id, user.id)
    ctx = Ctx(SCOTT)  # In the reminder's channel: the reply is the alert
    run(c.campaign_skip.callback(ctx, alias="Game"))
    alert = ctx.last
    assert alert.content.startswith("⏭️ **Game** is off on Mon 28 Sep (skipped by <@1>). Next session: <t:")
    assert alert.content.endswith("<@2> <@3>") and not alert.private
    assert [u.id for u in alert.allowed_mentions.users] == [DAVE.id, PAT.id] and alert.allowed_mentions.everyone is False


def test_a_skip_from_another_channel_posts_the_alert_in_the_reminders(game, bot):
    react(True, remind("mondays at 1900").id, DAVE.id)
    ctx = Ctx(SCOTT, channel=Channel(600))
    run(c.campaign_skip.callback(ctx, alias="Game"))
    alert = bot.channels[500].sent[-1]
    assert alert.content.startswith("⏭️ **Game** is off") and alert.content.endswith("<@2>")
    assert [u.id for u in alert.allowed_mentions.users] == [DAVE.id]
    assert "Posted in <#500>, pinging the 1 with a 🔔." in ctx.last.content


def test_a_reschedule_that_moves_the_game_pings_but_a_new_warning_doesnt(game, bot):
    react(True, remind("mondays at 1900").id, DAVE.id)
    ctx = Ctx(SCOTT)
    run(c.campaign_reschedule.callback(ctx, "Game", change="30 minutes before"))
    assert "updated" in ctx.last.content and ctx.last.allowed_mentions is c.NO_PINGS  # Same game, quietly
    ctx = Ctx(SCOTT)
    run(c.campaign_reschedule.callback(ctx, "Game", change="tuesdays 8pm"))
    alert = ctx.last
    assert alert.content.startswith("🗓️ **Game** has moved (by <@1>): Tuesdays at 20:00. Next session: <t:")
    assert alert.content.endswith("<@2>") and [u.id for u in alert.allowed_mentions.users] == [DAVE.id]


def message(author, alert, note="", slash=True, channel=None):
    ctx = Ctx(author, slash=slash, channel=channel)
    run(c.campaign_message.callback(ctx, "Game", alert, note=note))
    return ctx


def test_messaging_the_group_pings_everyone_with_a_bell(game, bot):
    message_id = remind("mondays at 1900").id
    react(True, message_id, DAVE.id)
    react(True, message_id, PAT.id)
    sent = message(SCOTT, "rp", "Bring snacks @everyone").last
    assert sent.content.startswith("**Game**: 🎭 This session will be RP heavy: bring your best voices. (from <@1>)")
    assert "> Bring snacks @​everyone" in sent.content and "-# Next session: <t:" in sent.content
    assert sent.content.endswith("<@2> <@3>") and [u.id for u in sent.allowed_mentions.users] == [DAVE.id, PAT.id]
    assert sent.allowed_mentions.everyone is False and not sent.private


def test_a_headcount_gets_ticks_and_a_player_can_say_theyre_late(game, bot):
    react(True, remind("mondays at 1900").id, DAVE.id)
    assert message(SCOTT, "headcount").last.reactions == ["✅", "❌"]
    late = message(DAVE, "late").last  # Dave's in the group: he can, and isn't pinged by his own
    assert "Running a bit late" in late.content and late.allowed_mentions.users == []
    assert "Only the group" in message(PAT, "late").last.content  # Pat isn't


def test_a_message_typed_or_from_elsewhere(game, bot):
    react(True, remind("mondays at 1900").id, DAVE.id)
    typed = message(SCOTT, "combat", "heavy, big boss tonight", slash=False).last
    assert "combat heavy" in typed.content and "> big boss tonight" in typed.content
    assert "Which alert?" in message(SCOTT, "dance party").last.content
    elsewhere = message(SCOTT, "who's in", channel=Channel(600))
    assert bot.channels[500].sent[-1].reactions == ["✅", "❌"]
    assert "Sent to the **Game** group: 🙋 Who's in?" in elsewhere.last.content


def test_messaging_needs_a_reminder(game):
    assert "doesn't have a reminder" in message(SCOTT, "rp").last.content


def test_weekly_skip(game):
    remind("mondays at 1900")
    run(c.campaign_skip.callback(Ctx(SCOTT), alias="Game"))
    assert sessions(2) == ["Mon 05 Oct 19:00", "Mon 12 Oct 19:00"]


def test_reschedule_keeps_subscribers_and_message(game):
    message_id = remind("every other monday at 7pm from 19 oct").id
    react(True, message_id, DAVE.id)
    assert "has moved" in reschedule("next 2 nov").content  # Moved the game: Dave's pinged
    assert sessions(2) == ["Mon 02 Nov 19:00", "Mon 16 Nov 19:00"]
    reschedule("every other thursday 8pm from 5 nov")
    assert sessions(2) == ["Thu 05 Nov 20:00", "Thu 19 Nov 20:00"]
    assert c.subscribers(current().id) == [DAVE.id] and current().message_id == message_id


@pytest.mark.parametrize("change, message", [
    ("next 3 nov", "isn't on the schedule"),
    ("next 1/9/2026", "in the past"),
    ("whenever", "Add a time"),
    ("remind", "What should change?"),
])
def test_reschedule_problems(game, change, message):
    remind("every other monday at 7pm from 19 oct")
    assert message in reschedule(change).content


def test_changing_just_the_warning(game):
    remind("mondays at 1900, 15 minutes before")
    reschedule("reminder 30 minutes before")
    assert local(current().next_run_at) == "Mon 28 Sep 18:30"
    game.set(datetime(2026, 9, 28, 17, 40, tzinfo=timezone.utc))  # 18:40: an hour before 19:00 has passed
    reschedule("1 hour before")
    assert local(current().next_run_at) == "Mon 05 Oct 18:00"
    reschedule("mondays 8pm")  # a new schedule keeps the warning
    assert current().lead_minutes == 60


def test_zero_warning_says_starting_now(game, bot):
    remind("mondays at 1900")
    game.set(current().next_run_at)
    run(c.reminder_loop.coro())
    assert bot.channels[500].sent[-1].content.startswith("⏰ **Game** is starting now!")


def test_permissions(game):
    remind("mondays at 1900")
    assert "Only whoever set the reminder" in reschedule("next 5 oct", author=PAT).content
    ctx = Ctx(PAT)
    run(c.campaign_unremind.callback(ctx, alias="Game"))
    assert "Only whoever set the reminder" in ctx.last.content
    assert "Reminder set" in remind("mondays at 1800", author=MOD).content  # mods may replace it


def test_rename_keeps_reminder_and_remove_deletes_it(game):
    react(True, remind("mondays at 1900").id, DAVE.id)
    run(c.campaign_edit.callback(Ctx(SCOTT), "Game", rename="Game night"))
    assert c.get_reminder(111, "Game night") is not None
    run(c.campaign_remove.callback(Ctx(SCOTT), alias="Game night"))
    assert db.conn.execute("SELECT COUNT(*) FROM campaign_reminders").fetchone()[0] == 0
    assert db.conn.execute("SELECT COUNT(*) FROM campaign_reminder_subscribers").fetchone()[0] == 0


def test_show_includes_reminder(game):
    remind("mondays at 1900, 15 minutes before")
    ctx = Ctx(DAVE)
    run(c.campaign_show.callback(ctx, alias="Game"))
    assert "**Reminder:** ⏰ Mondays at 19:00, pings 15 minutes before" in ctx.last.embed.description


def test_a_reminder_the_network_ate_is_sent_when_it_comes_back(game, bot, monkeypatch):
    """A storm takes the internet out at reminder time: it's not skipped to next week, but sent once it's back."""
    import socket
    react(True, remind("mondays at 1900, 15 minutes before").id, DAVE.id)
    due = current().next_run_at
    channel = bot.channels[500]
    real_send = channel.send

    async def no_network(*args, **kwargs):
        raise socket.gaierror(-3, "Temporary failure in name resolution")
    monkeypatch.setattr(channel, "send", no_network)
    game.set(due + timedelta(seconds=20))
    run(c.reminder_loop.coro())
    assert current().next_run_at == due  # Still due
    monkeypatch.setattr(channel, "send", real_send)
    game.set(due + timedelta(minutes=5))  # The network's back
    run(c.reminder_loop.coro())
    assert channel.sent[-1].content.startswith("⏰ **Game** starts <t:") and "<@2>" in channel.sent[-1].content
    assert local(current().next_run_at) == "Mon 05 Oct 18:45"


def test_a_reminder_that_breaks_doesnt_stop_the_others(game, bot, monkeypatch, caplog):
    remind("mondays at 1900")
    monkeypatch.setattr(c, "send_reminder", lambda reminder: (_ for _ in ()).throw(ValueError("a bug")))
    game.set(current().next_run_at + timedelta(seconds=20))
    caplog.set_level("ERROR", logger="ktdi")
    run(c.reminder_loop.coro())  # Doesn't raise: the loop carries on
    assert "failed" in caplog.text and local(current().next_run_at) == "Mon 05 Oct 19:00"
