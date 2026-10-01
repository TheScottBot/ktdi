"""The committee's funds (ktdi.features.committee)."""

import random

from ktdi import db
from ktdi.features import committee, fun
from tests.fakes import Ctx, Guild, User, run

SCOTT, DAVE = User(1, "scott"), User(2, "dave")
A, B = Guild(111, "Hangout"), Guild(222, "Other")


def test_every_kind_of_payment_funds_the_committee():
    assert committee.balance(111) == 0
    fun.record_bribe(111, SCOTT.id, 100)  # an old bribe, from before the committee kept accounts
    fun.record_spray(111, DAVE.id)
    fun.record_spray(111, DAVE.id)
    run(fun.expunge.callback(Ctx(DAVE), 250))
    run(fun.bail.callback(Ctx(SCOTT), DAVE, 50))
    assert committee.total_paid_in(111) == 400 and committee.balance(111) == 400


def test_funds_embed():
    fun.record_bribe(111, SCOTT.id, 1_500)
    ctx = Ctx(SCOTT)
    run(committee.committee_funds.callback(ctx))
    embed = ctx.last.embed
    assert embed.description == "## $1,500"
    assert {f.name: f.value for f in embed.fields} == {"Paid in": "$1,500", "Spent": "$0"}
    assert embed.footer.text in committee.FUNDS_LINES


def test_spending():
    fun.record_bribe(111, SCOTT.id, 1_000)
    ctx = Ctx(DAVE)
    run(committee.committee_spend.callback(ctx, 300, item="  pizza for the next session "))
    reply = ctx.last
    assert "pizza for the next session" in reply.content and "$300" in reply.content and "<@2>" in reply.content
    assert "$700 left in the committee's funds." in reply.content
    assert reply.allowed_mentions.users is False  # no pings, even if someone puts an @mention in the item
    assert committee.balance(111) == 700 and committee.total_spent(111, DAVE.id) == 300

    run(committee.committee_funds.callback(ctx))
    fields = {f.name: f.value for f in ctx.last.embed.fields}
    assert fields["Spent"] == "$300" and "**$300** on pizza for the next session, by <@2>" in fields["Recent spending"]

    run(fun.rapsheet.callback(ctx, DAVE))
    assert "🧾 Spent $300 of the committee's funds." in ctx.last.content


def test_cant_overspend_or_spend_on_nothing():
    fun.record_bribe(111, SCOTT.id, 100)
    ctx = Ctx(DAVE)
    run(committee.committee_spend.callback(ctx, 101, item="a gold-plated d20"))
    assert "only has $100" in ctx.last.content and ctx.last.private
    run(committee.committee_spend.callback(ctx, 10, item="   "))
    assert "Spend it on what?" in ctx.last.content and ctx.last.private
    assert committee.balance(111) == 100


def test_long_items_are_cut_short():
    fun.record_bribe(111, SCOTT.id, 100)
    run(committee.committee_spend.callback(Ctx(DAVE), 1, item="x" * 500))
    assert len(committee.recent_spending(111, 1)[0].item) == committee.ITEM_MAX_LENGTH


def test_ledger():
    ctx = Ctx(SCOTT)
    run(committee.committee_ledger.callback(ctx))
    assert "hasn't spent anything yet" in ctx.last.content
    fun.record_bribe(111, SCOTT.id, 100)
    for item in ("dice", "snacks", "a rubber chicken"):
        run(committee.committee_spend.callback(Ctx(SCOTT), 10, item=item))
    run(committee.committee_ledger.callback(ctx))
    lines = ctx.last.embed.description.splitlines()
    assert [line.split(" on ")[1].split(",")[0] for line in lines] == ["a rubber chicken", "snacks", "dice"]
    assert ctx.last.embed.footer.text == "Last 3 purchases. $30 spent in total, $70 left."


def test_proposals(monkeypatch):
    assert "the committee is broke" in committee.proposal_text(111)
    fun.record_bribe(111, SCOTT.id, 100)
    monkeypatch.setattr(committee, "PROPOSALS", [("an actual spray bottle", 4), ("a small island", 2_500_000)])
    texts = {committee.proposal_text(111, random.Random(seed)) for seed in range(20)}
    assert any("would buy **25** of them" in t for t in texts)
    assert any("$2,499,900 short" in t for t in texts)


def test_bare_committee_shows_the_funds():
    ctx = Ctx(SCOTT, slash=False)
    run(committee.committee_group.callback(ctx))
    assert ctx.last.embed.title == "🏛️ The committee's funds"


def test_shared_servers_share_one_committee():
    fun.record_bribe(A.id, SCOTT.id, 100)
    fun.record_bribe(B.id, SCOTT.id, 100)
    committee.record_spend(B.id, 50, "dice", SCOTT.id)
    assert committee.balance(A.id) == 150
    db.set_shared(B.id, False)  # B keeps its own books
    assert committee.balance(A.id) == 100 and committee.balance(B.id) == 50
