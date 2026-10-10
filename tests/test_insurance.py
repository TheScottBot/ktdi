"""/insurance: spray insurance and the committee's two clocks (ktdi.features.insurance, ktdi.lib.insurance)."""

import random
import types
from datetime import datetime, timedelta, timezone

import pytest

from ktdi.features import committee, fun, futures, insurance
from ktdi.lib import insurance as clocks
from tests.fakes import Channel, Ctx, Guild, User, run

SCOTT, DAVE = User(1, "scott"), User(2, "dave")
NOON = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)  # Minute 0


def spec_clocks(user_id, minute):
    """The spec's algorithm, written out separately, to check the real one against."""
    digits = [int(d) for d in str(user_id)]
    tens, ones = divmod(minute, 10)
    microwave_seed = 3 * digits[-1] + 5 * digits[-4] + 7 * digits[-7] + 11 * digits[-10]
    car_seed = 11 * digits[-2] + 7 * digits[-5] + 5 * digits[-8] + 3 * digits[-11]
    microwave = 120 + (13 * microwave_seed + 137 * tens + 83 * ones + 71 * tens * ones + 19 * tens * tens
                       + 23 * ones * ones) % 480
    error = (17 * car_seed + 31 * tens + 37 * ones + 11 * tens * ones + 3 * tens * tens + 7 * ones * ones) % 41 - 20
    return microwave, max(120, min(599, round(microwave * (100 + error) / 100)))


# --- The clocks ---
def test_clocks_follow_the_spec():
    rng = random.Random(7)
    for user_id in [rng.randrange(10 ** 16, 10 ** 19) for _ in range(300)] + [140123456789012345]:
        for minute in range(60):
            assert clocks.clocks(user_id, minute) == spec_clocks(user_id, minute)
    assert [clocks.clocks(140123456789012345, m) for m in (0, 7, 23, 59)] == [(202, 240), (470, 498), (474, 498),
                                                                             (447, 465)]


def test_clocks_stay_in_range_and_within_20_percent():
    rng = random.Random(8)
    for user_id in [rng.randrange(10 ** 16, 10 ** 19) for _ in range(300)] + [1, 2, 99]:
        for minute in range(60):
            microwave, car = clocks.clocks(user_id, minute)
            assert 120 <= microwave <= 599 and 120 <= car <= 599
            assert abs(car - microwave) <= 0.2 * microwave + 0.5  # rounding
            assert -20 <= clocks.clock_error(user_id, minute) <= 20


def test_clocks_are_predictable_and_either_can_run_out_first():
    assert clocks.clocks(140123456789012345, 23) == clocks.clocks(140123456789012345, 23)
    pairs = [clocks.clocks(user_id, minute) for user_id in range(10 ** 17, 10 ** 17 + 50) for minute in range(60)]
    assert any(car < microwave for microwave, car in pairs) and any(car > microwave for microwave, car in pairs)


def test_short_ids_are_padded():
    assert clocks.id_digits(12) == [0] * 17 + [1, 2]
    assert 120 <= clocks.microwave_clock(1, 30) <= 599


# --- Buying and claiming ---
def someone(car_slower: bool) -> User:
    """A user whose car clock runs out after (or before) the microwave when buying at NOON."""
    for user_id in range(10, 10_000):
        microwave, car = clocks.clocks(user_id, NOON.minute)
        if (car > microwave + 10) if car_slower else (car < microwave - 10):
            return User(user_id, f"user{user_id}")
    raise AssertionError("nobody found")


@pytest.fixture
def at(clock):
    """at(seconds) sets the clock to that many seconds after noon."""
    def set_time(seconds):
        clock.set(NOON + timedelta(seconds=seconds), insurance, futures)
    set_time(0)
    return set_time


def buy(user):
    ctx = Ctx(user)
    run(insurance.insurance_buy.callback(ctx))
    return ctx.last.content


def spray(target, by=SCOTT):
    ctx = Ctx(by)
    run(fun.spray.callback(ctx, target))
    return ctx.last.content


def test_buying_a_policy(at):
    user = someone(car_slower=True)
    microwave, car = clocks.clocks(user.id, 0)
    text = buy(user)
    when = int((NOON + timedelta(seconds=car)).timestamp())
    assert "$1,000" in text and user.mention in text
    assert text.endswith(f"⏱️ Covered until <t:{when}:T> (<t:{when}:R>).")  # the car clock, never the microwave
    assert committee.balance(111) == 1_000 and fun.get_bribe_stats(111, user.id) == (1, 1_000)
    at(60)
    assert buy(user).endswith("Their old policy has been cancelled. No refunds.")
    assert committee.balance(111) == 2_000


def test_sprays_are_forgiven_until_the_microwave_runs_out(at):
    user = someone(car_slower=True)
    microwave, car = clocks.clocks(user.id, 0)
    buy(user)
    at(microwave - 1)
    assert "Claim approved" in spray(user)
    assert fun.get_spray_count(111, user.id) == 0 and insurance.claim_count(111, user.id) == 1
    at(microwave)  # The real cover's gone, but the countdown's still running.
    assert "the committee goes by the microwave" in spray(user)
    assert fun.get_spray_count(111, user.id) == 1
    at(car + 1)  # Both gone: an ordinary spray.
    assert spray(user) == f"{user.mention} {fun.SPRAY_GIF_URL}"
    assert fun.get_spray_count(111, user.id) == 2
    ctx = Ctx(SCOTT)
    run(fun.rapsheet.callback(ctx, user))
    assert "🛡️ Insurance covered 1 spray." in ctx.last.content and "Sprayed 2 times." in ctx.last.content


def test_cover_can_outlast_the_countdown(at):
    user = someone(car_slower=False)
    microwave, car = clocks.clocks(user.id, 0)
    buy(user)
    at(car + 1)
    ctx = Ctx(user)
    run(insurance.insurance_status.callback(ctx))
    assert "policy ran out" in ctx.last.content
    assert "Claim approved" in spray(user)  # Still covered, whatever the car says.
    assert fun.get_spray_count(111, user.id) == 0


def test_a_new_policy_replaces_the_old_one(at):
    user = someone(car_slower=True)
    buy(user)
    first = insurance.latest_policy(111, user.id)
    at(30 * 60)  # A different minute, so different clocks.
    buy(user)
    second = insurance.latest_policy(111, user.id)
    assert second[0] != first[0] and second[1] == NOON + timedelta(seconds=30 * 60 + clocks.microwave_clock(user.id, 30))


def test_uninsured_sprays_say_nothing(at):
    assert spray(DAVE) == f"{DAVE.mention} {fun.SPRAY_GIF_URL}"
    assert fun.get_spray_count(111, DAVE.id) == 1 and insurance.claim_count(111, DAVE.id) == 0


def test_covered_sprays_still_pay_out_spray_futures(at, bot, monkeypatch):
    monkeypatch.setattr(futures.random, "randint", lambda low, high: 1)
    user = someone(car_slower=True)
    pit = bot.add_channel(Channel(500, Guild()))
    fun.record_spray(111, DAVE.id)  # Dave has a spray to win back.
    run(futures.sprayfutures.callback(Ctx(DAVE, channel=pit), user, 1, 1))
    buy(user)
    spray(user, by=SCOTT)
    assert "Spray future paid out" in pit.sent[-1].content
    assert fun.get_spray_count(111, DAVE.id) == 0 and fun.get_spray_count(111, user.id) == 0


def test_the_spray_reaction_and_tdoi_are_covered_too(at, bot):
    user = someone(car_slower=True)
    buy(user)
    channel = bot.add_channel(Channel(700, Guild()))
    payload = types.SimpleNamespace(emoji="💦", user_id=SCOTT.id, channel_id=700, guild_id=111,
                                    message_author_id=user.id, member=SCOTT)
    run(fun.spray_reaction(payload))
    assert "Claim approved" in channel.sent[-1].content
    insurance.db.set_whospray_user(111, DAVE.id)
    ctx = Ctx(user)
    run(fun.tdoi.callback(ctx))
    assert "Claim approved" in ctx.last.content
    assert fun.get_spray_count(111, user.id) == 0 and insurance.claim_count(111, user.id) == 2


def test_bad_and_badbonk_are_covered_too(at):
    user = someone(car_slower=True)
    microwave, car = clocks.clocks(user.id, 0)
    buy(user)
    ctx = Ctx(SCOTT)
    run(fun.bad.callback(ctx, user))
    assert "Claim approved" in ctx.last.content
    run(fun.badbonk.callback(ctx, user))
    assert "Claim approved" in ctx.last.content
    spray(user)
    assert fun.get_bad_count(111, user.id) == 0
    assert insurance.claim_count(111, user.id, "bad") == 2 and insurance.claim_count(111, user.id, "spray") == 1
    at(microwave)  # Run out, whatever the countdown says.
    run(fun.bad.callback(ctx, user))
    assert "goes by the microwave" in ctx.last.content and fun.get_bad_count(111, user.id) == 1
    run(fun.rapsheet.callback(ctx, user))
    assert "🛡️ Insurance covered 1 spray and being bad 2 times." in ctx.last.content
    run(insurance.insurance_status.callback(ctx, user))
    assert ctx.last.content.endswith("-# Covered so far: 1 spray and being bad 2 times.")


def test_status(at):
    ctx = Ctx(SCOTT)
    run(insurance.insurance_status.callback(ctx, DAVE))
    assert "dave has never bought spray insurance" in ctx.last.content
    user = someone(car_slower=True)
    car = clocks.car_clock(user.id, 0)
    buy(user)
    run(insurance.insurance_status.callback(ctx, user))
    when = int((NOON + timedelta(seconds=car)).timestamp())
    assert ctx.last.content == f"🛡️ {user.display_name}'s policy runs out <t:{when}:R> (<t:{when}:T>)."


def test_complain(monkeypatch):
    monkeypatch.setattr(insurance.random, "choice", lambda options: options[7])
    ctx = Ctx(SCOTT)
    run(insurance.insurance_complain.callback(ctx))
    assert ctx.last.content == "📞 I think Dave normally sorts that."
