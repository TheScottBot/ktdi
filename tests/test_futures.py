"""/sprayfutures: betting on someone getting sprayed (ktdi.features.futures)."""

import types
from datetime import datetime, timedelta, timezone

import pytest

from ktdi import db
from ktdi.features import fun, futures
from tests.fakes import Channel, Ctx, Guild, User, run

SCOTT, DAVE, PAT, AMY = User(1, "scott"), User(2, "dave"), User(3, "pat"), User(4, "amy")
NOON = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def at(clock):
    """at(minutes) sets the clock to that many minutes after noon."""
    def set_time(minutes):
        clock.set(NOON + timedelta(minutes=minutes), futures)
    set_time(0)
    return set_time


@pytest.fixture(autouse=True)
def low_rate(monkeypatch):
    """The daily rate is random; pin it at 1%, which leaves small stakes unchanged (3 at 1% is still 3)."""
    monkeypatch.setattr(futures.random, "randint", lambda low, high: 1)


def set_rate(rate, moment=NOON):
    db.conn.execute("INSERT OR REPLACE INTO spray_rates (day, rate, set_at) VALUES (?, ?, ?)",
                    (futures.rate_day(moment).isoformat(), rate, moment.isoformat()))


@pytest.fixture
def pit(bot):
    """The channel bets are placed in (where they're settled too)."""
    return bot.add_channel(Channel(500, Guild()))


def bet(user, target, stake=1, channel=None, hours=1):
    ctx = Ctx(user, channel=channel)
    run(futures.sprayfutures.callback(ctx, target, stake, hours))
    return ctx.last


def spray(user, target):
    run(fun.spray.callback(Ctx(user), target))


def announced(channel):
    """Everything the bot posted in the channel (bets are replies; payouts and expiries are posted there)."""
    return "\n".join(m.content or "" for m in channel.sent)


def sprays_on(user):
    return fun.get_spray_count(111, user.id)


def test_placing_a_bet(at, pit):
    reply = bet(SCOTT, DAVE, 2, channel=pit)
    expires = int((NOON + timedelta(hours=1)).timestamp())
    assert reply.content == (f"📈 <@1> is betting <@2> gets sprayed by <t:{expires}:t> (<t:{expires}:R>): 2 sprays, "
                             "plus today's 1% spray interest = **2 sprays** on the line.\n-# If someone else sprays them "
                             "before then, 2 sprays come off <@1>'s record. If not, 2 sprays go on. Spraying them "
                             "yourself doesn't count.")
    assert reply.allowed_mentions.users is False  # no pings
    assert "already got a future on dave" in bet(SCOTT, DAVE, channel=pit).content
    assert "1 spray comes off" in bet(SCOTT, PAT, channel=pit).content  # a different target is fine


def test_refusals(at):
    assert "can't take out futures on yourself" in bet(SCOTT, SCOTT).content
    robot = User(9, "robot")
    robot.bot = True
    assert "Bots don't get sprayed" in bet(SCOTT, robot).content
    assert db.conn.execute("SELECT COUNT(*) FROM spray_futures").fetchone()[0] == 0


def test_someone_else_spraying_them_pays_out(at, pit):
    for _ in range(3):
        fun.record_spray(111, SCOTT.id)
    bet(SCOTT, DAVE, 2, channel=pit)
    at(30)
    spray(PAT, DAVE)
    assert pit.sent[-1].content == ("📈 **Spray future paid out!** <@3> sprayed <@2>, so 2 sprays come off <@1>'s "
                                    "record.")
    assert pit.sent[-1].allowed_mentions.users is False
    assert sprays_on(SCOTT) == 1
    spray(AMY, DAVE)  # already settled: nothing more
    assert sprays_on(SCOTT) == 1 and announced(pit).count("paid out") == 1


def test_you_cant_cash_in_your_own_spray(at, pit):
    for _ in range(3):
        fun.record_spray(111, SCOTT.id)
    bet(SCOTT, DAVE, channel=pit)
    spray(SCOTT, DAVE)  # embezzlement attempt
    assert sprays_on(SCOTT) == 3 and "paid out" not in announced(pit)
    reaction = types.SimpleNamespace(emoji="💦", user_id=SCOTT.id, channel_id=500, guild_id=111,
                                     message_author_id=DAVE.id, member=SCOTT)
    run(fun.spray_reaction(reaction))  # nor by reaction
    assert sprays_on(SCOTT) == 3
    reaction.user_id, reaction.member = AMY.id, AMY  # but someone else's 💦 counts
    run(fun.spray_reaction(reaction))
    assert sprays_on(SCOTT) == 2 and "<@4> sprayed <@2>" in pit.sent[-1].content


def test_tdoi_counts_as_someone_else(at, pit):
    db.set_whospray_user(111, PAT.id)
    fun.record_spray(111, SCOTT.id)
    bet(SCOTT, DAVE, channel=pit)
    run(fun.tdoi.callback(Ctx(DAVE)))  # Dave sprays himself on the Don's orders: not Scott's doing
    assert sprays_on(SCOTT) == 0 and "<@2> sprayed <@2>" in pit.sent[-1].content


def test_winning_never_goes_below_a_clean_record(at, pit):
    fun.record_spray(111, SCOTT.id)
    bet(SCOTT, DAVE, 3, channel=pit)
    spray(PAT, DAVE)
    assert pit.sent[-1].content.endswith("1 spray comes off <@1>'s record. (They had 3 on the line, but only 1 to lose.)")
    assert sprays_on(SCOTT) == 0
    fun.record_spray(111, SCOTT.id)  # no credit banked: the next spray counts
    assert sprays_on(SCOTT) == 1

    bet(AMY, PAT, channel=pit)  # Amy's record is clean
    spray(DAVE, PAT)
    assert "their record was already clean" in pit.sent[-1].content


def test_running_out_of_time_costs_the_stake(at, pit):
    bet(SCOTT, DAVE, 3, channel=pit)
    bet(AMY, DAVE, channel=pit)
    at(59)
    assert run(futures.announce(futures.expire(futures.now()))) is None and sprays_on(SCOTT) == 0  # not yet
    at(60)
    run(futures.announce(futures.expire(futures.now())))
    assert pit.sent[-2].content == ("📉 **Spray future expired.** Nobody sprayed <@2> in time, so 3 sprays go on "
                                    "<@1>'s record.")
    assert pit.sent[-1].content.endswith("so 1 spray goes on <@4>'s record.")
    assert sprays_on(SCOTT) == 3 and sprays_on(AMY) == 1
    spray(PAT, DAVE)  # too late now
    assert sprays_on(SCOTT) == 3


def test_a_spray_after_the_hour_but_before_the_check_doesnt_count(at, pit):
    bet(SCOTT, DAVE, channel=pit)
    at(61)
    spray(PAT, DAVE)
    assert sprays_on(SCOTT) == 0 and "paid out" not in announced(pit)
    run(futures.announce(futures.expire(futures.now())))
    assert sprays_on(SCOTT) == 1


def test_rap_sheet(at, pit):
    for _ in range(2):
        fun.record_spray(111, SCOTT.id)
    bet(SCOTT, DAVE, 2, channel=pit)
    spray(PAT, DAVE)
    bet(SCOTT, AMY, channel=pit)
    at(61)
    run(futures.announce(futures.expire(futures.now())))
    ctx = Ctx(DAVE)
    run(fun.rapsheet.callback(ctx, SCOTT))
    sheet = ctx.last.content
    assert "Sprayed 1 time." in sheet  # 2, minus 2 won, plus 1 lost
    assert "📈 Spray futures: 1 won (2 sprays off), 1 lost (1 spray on)." in sheet


def test_shared_state(at, pit):
    fun.record_spray(222, SCOTT.id)
    bet(SCOTT, DAVE, channel=pit)  # placed on server 111
    run(fun.spray.callback(Ctx(PAT, Guild(222)), DAVE))  # sprayed on server 222, shared with 111
    assert fun.get_spray_count(111, SCOTT.id) == 0
    db.set_shared(222, False)  # 222 goes its own way: the win was on 111's books
    assert fun.get_spray_count(222, SCOTT.id) == 1


def test_open_bets_survive_a_restart(at, monkeypatch):
    bet(SCOTT, DAVE)
    started = []
    monkeypatch.setattr(futures.expiry_loop, "start", lambda: started.append(True))
    run(futures.setup(types.SimpleNamespace(add_command=lambda command: None)))
    assert started == [True]  # the expiry check restarts on its own


# --- Hours and the daily spray interest rate ---
def test_hours_multiply_the_stake_and_the_time(at, pit):
    set_rate(15)
    reply = bet(SCOTT, DAVE, 2, channel=pit, hours=3)  # 2 x 3 = 6, plus 15% = 6.9: 7
    expires = int((NOON + timedelta(hours=3)).timestamp())
    assert f"gets sprayed by <t:{expires}:t>" in reply.content
    assert "2 sprays × 3 hours, plus today's 15% spray interest = **7 sprays** on the line." in reply.content
    at(179)
    run(futures.announce(futures.expire(futures.now())))
    assert sprays_on(SCOTT) == 0  # still open at 2h59m
    at(180)
    run(futures.announce(futures.expire(futures.now())))
    assert sprays_on(SCOTT) == 7 and "so 7 sprays go on <@1>'s record" in announced(pit)


def test_a_win_pays_the_whole_amount(at, pit):
    set_rate(20)
    for _ in range(10):
        fun.record_spray(111, SCOTT.id)
    bet(SCOTT, DAVE, 3, channel=pit, hours=2)  # 3 x 2 = 6, plus 20% = 7.2: 7
    at(100)
    spray(PAT, DAVE)
    assert sprays_on(SCOTT) == 3 and "7 sprays come off <@1>'s record" in announced(pit)


@pytest.mark.parametrize("stake, hours, rate, amount", [
    (1, 1, 1, 1), (1, 1, 20, 1), (2, 1, 20, 2), (3, 1, 20, 4), (2, 3, 15, 7), (10, 24, 20, 288), (5, 2, 5, 11),
])
def test_amount_at_stake(stake, hours, rate, amount):
    # stake x hours, plus interest, rounded to the nearest spray (a half rounds up: 5 x 2 at 5% = 10.5 -> 11)
    assert futures.amount_at_stake(stake, hours, rate) == amount


def test_the_rate_is_fixed_when_you_bet(at, pit):
    set_rate(20)
    bet(SCOTT, DAVE, 3, channel=pit)  # 3.6: 4
    set_rate(1, NOON + timedelta(days=1))
    at(60 * 24)  # the next day, at a new rate, the bet has long expired at the old one
    run(futures.announce(futures.expire(futures.now())))
    assert sprays_on(SCOTT) == 4


def test_a_new_rate_each_day_at_the_set_time(monkeypatch):
    from ktdi import config
    from zoneinfo import ZoneInfo
    from datetime import time
    monkeypatch.setattr(config, "BOT_TIMEZONE", ZoneInfo("Europe/London"))
    monkeypatch.setattr(config, "SPRAY_RATE_TIME", time(18, 0))
    rates = iter([7, 13])
    monkeypatch.setattr(futures.random, "randint", lambda low, high: next(rates))
    before = datetime(2026, 10, 9, 16, 59, tzinfo=timezone.utc)  # 17:59 in London (BST)
    after = datetime(2026, 10, 9, 17, 0, tzinfo=timezone.utc)  # 18:00 in London
    assert futures.rate_day(before).isoformat() == "2026-10-08" and futures.rate_day(after).isoformat() == "2026-10-09"
    assert futures.todays_rate(before) == 7 and futures.todays_rate(before - timedelta(hours=5)) == 7  # stays put
    assert futures.todays_rate(after) == 13
    assert futures.next_rate_at(after) == datetime(2026, 10, 10, 18, 0, tzinfo=ZoneInfo("Europe/London"))


def test_rates_are_whole_numbers_from_1_to_20(monkeypatch):
    seen = []
    monkeypatch.setattr(futures.random, "randint", lambda low, high: seen.append((low, high)) or high)
    assert futures.todays_rate(NOON) == 20 and seen == [(1, 20)]


def test_sprayrate(at):
    set_rate(12)
    ctx = Ctx(SCOTT)
    run(futures.sprayrate.callback(ctx))
    next_rate = int(futures.next_rate_at(NOON).timestamp())
    assert ctx.last.content == ("📊 Today's spray interest rate is **12%**. Every spray future placed today pays (or "
                                f"costs) 12% on top.\n-# The next rate is set <t:{next_rate}:R>.")


def test_spray_rate_time_setting(monkeypatch):
    from ktdi import config
    from datetime import time
    monkeypatch.setenv("SPRAY_RATE_TIME", "18:30")
    assert config.time_setting("SPRAY_RATE_TIME", "00:00") == time(18, 30)
    monkeypatch.setenv("SPRAY_RATE_TIME", "teatime")
    assert config.time_setting("SPRAY_RATE_TIME", "00:00") == time(0, 0)
    assert config.SPRAY_RATE_TIME == time(0, 0)  # midnight unless .env says otherwise
