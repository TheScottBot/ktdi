"""/wars: bursts of sprays, /bad and /badbonk recorded as wars or special military operations, and reported afterwards
(ktdi.features.wars)."""

import types
from datetime import datetime, timedelta, timezone

import pytest

from ktdi import db
from ktdi.features import fun, insurance, wars
from tests.fakes import Channel, Ctx, Guild, User, run

SCOTT, DAVE, PAT = User(1, "scott"), User(2, "dave"), User(3, "pat")
NAMES = {1: "Scott", 2: "Dave", 3: "Pat"}
REAL_MEMBER_NAME = wars.member_name  # Before the names fixture swaps it out.
EVENING = datetime(2026, 10, 9, 20, 42, tzinfo=timezone.utc)  # A Friday; 21:42 in London (BST)


@pytest.fixture
def at(clock):
    """at(seconds) sets the clock to that many seconds after 21:42."""
    def set_time(seconds):
        clock.set(EVENING + timedelta(seconds=seconds), wars, insurance)
    set_time(0)
    return set_time


@pytest.fixture
def front(bot):
    """The channel the fighting happens in."""
    return bot.add_channel(Channel(600, Guild()))


@pytest.fixture(autouse=True)
def names(monkeypatch):
    async def member_name(guild_id, user_id):
        return NAMES[user_id]
    monkeypatch.setattr(wars, "member_name", member_name)


def spray(user, target, channel):
    run(fun.spray.callback(Ctx(user, channel=channel), target))


def bad(user, target, channel, bonk=False):
    run((fun.badbonk if bonk else fun.bad).callback(Ctx(user, channel=channel), target))


def skirmish(at, channel, start=0, acts=8):
    """Scott and Dave go at each other, one act every 20 seconds."""
    for i in range(acts):
        at(start + 20 * i)
        if i % 2:
            bad(DAVE, SCOTT, channel, bonk=i % 4 == 1)
        else:
            spray(SCOTT, DAVE, channel)


def spree(at, channel, acts=4, target=PAT, start=0):
    """Scott, on his own, bads someone every 10 seconds."""
    for i in range(acts):
        at(start + 10 * i)
        bad(SCOTT, target, channel)


def finish(at, seconds):
    """Let the ceasefire happen; returns the reports."""
    at(seconds)
    return run(wars.ceasefires(wars.now()))


def current(channel):
    return wars.get_war(wars.open_war(channel.id)[0])


def test_four_acts_is_a_conflict_but_nobody_is_told(at, front):
    skirmish(at, front, acts=3)
    assert wars.open_war(front.id) is None  # 3 isn't enough
    skirmish(at, front, start=60, acts=1)
    assert wars.open_war(front.id) is not None
    assert all(m.content is None or "war" not in m.content.lower() for m in front.sent)  # Not a word.
    assert wars.archived(111) == []  # Not in the archives until it's over.


def test_spread_out_isnt_a_conflict(at, front):
    for i in range(10):
        at(120 * i)  # one every 2 minutes: never 4 in 5 minutes
        spray(SCOTT if i % 2 else DAVE, PAT, front)
    assert wars.open_war(front.id) is None


def test_conflicts_stay_in_their_channel(at, bot, front):
    elsewhere = bot.add_channel(Channel(601, Guild(222)))
    for i in range(6):
        at(10 * i)
        spray(SCOTT if i % 2 else DAVE, PAT, front if i < 3 else elsewhere)
    assert wars.open_war(front.id) is None and wars.open_war(elsewhere.id) is None


def test_spraying_yourself_doesnt_count(at, front):
    db.set_whospray_user(111, PAT.id)
    for i in range(10):
        at(i)
        run(fun.tdoi.callback(Ctx(SCOTT if i % 2 else DAVE, channel=front)))
    assert db.conn.execute("SELECT COUNT(*) FROM hostilities").fetchone()[0] == 0


def test_the_war_report_after_the_ceasefire(at, front):
    skirmish(at, front)
    at(400)
    bad(PAT, SCOTT, front)  # Pat joins in late: it's all the same war
    assert finish(at, 400 + 9 * 60) == []  # 9 minutes quiet: not over yet
    [(channel_id, report)] = finish(at, 400 + 10 * 60)
    assert channel_id == front.id
    title = db.conn.execute("SELECT title FROM wars").fetchone()[0]
    assert report.title == title
    assert title in [t for t, _ in wars.title_options(wars.get_war(1), 1, {"persecuted": "Scott",
                                                                             "aggressor": "Scott"})]
    assert report.author.name == "KTDI Historical Records Office"
    assert report.description == "9 October 2026 · 21:42–21:48 · 7 minutes\nClassified as: **war**"
    assert [(f.name, f.value) for f in report.fields[:3]] == [("Hostilities", "9"), ("Belligerents", "3"),
                                                              ("Casualties", "9")]
    story = report.fields[3].value
    assert "<@1>" in story.split("\n")[0]  # Scott fired first: the cause
    assert "**Most aggressive combatant:** <@1> — 4 incidents" in story
    assert "**Most persecuted:** <@1> — 5 incidents" in story
    assert "**Arsenal:** 4 sprays, 3 bads, 2 badbonks" in story
    assert "Never fired back" not in story and "Insurance" not in story
    assert report.footer.text.startswith(wars.FOOTER) and report.footer.text.endswith("Number 1 in the archives.")
    assert wars.open_war(front.id) is None and wars.archived(111) == [1]


def test_one_person_on_a_spree_is_a_special_military_operation(at, front):
    spree(at, front)
    [(_, report)] = finish(at, 3600)
    war = wars.get_war(1)
    assert not war.is_war and war.kind == "special military operation"
    assert report.description.endswith("Classified as: **special military operation**")
    story = report.fields[3].value
    assert "**Commanding officer:** <@1> — 4 incidents" in story and "Most aggressive" not in story
    assert "**Never fired back:** <@3>" in story
    assert any(cause.format(first="<@1>") in story for cause in wars.OPERATION_CAUSES)
    assert any(outcome in story for outcome in wars.OPERATION_OUTCOMES)
    assert report.footer.text.startswith(wars.OPERATION_FOOTER)
    options = dict(wars.title_options(war, 1, {"persecuted": "Pat", "aggressor": "Scott"}))
    assert war.title in options
    assert options["The Annexation of Pat"] == 3 and options["The Badening of Pat"] == 3  # one target, all bads
    assert options["Scott's Special Military Operation"] == 2 and options["The Scott Doctrine"] == 2
    assert options["The First Special Military Operation"] == 2 and options["The Friday Night Raid"] == 2
    assert not any("War" in title for title in options)  # It is not a war, and must not be called one.


def test_firing_back_turns_an_operation_into_a_war(at, front):
    spree(at, front)
    at(60)
    spray(PAT, SCOTT, front)  # Pat retaliates
    assert current(front).is_war


def test_operations_and_wars_are_counted_separately(at, front):
    spree(at, front)
    finish(at, 3600)
    skirmish(at, front, start=7200)
    war = current(front)
    finish(at, 7200 + 3600)
    assert wars.get_war(war.id).title  # named
    options = dict(wars.title_options(wars.get_war(war.id), 1, {"persecuted": "Scott", "aggressor": "Scott"}))
    assert "The First Conflict of Unspecified Origin" in options  # The first war, though second in the archives
    assert wars.archived(111) == [1, 2]


def test_the_report_is_the_same_every_time(at, front):
    skirmish(at, front)
    [(_, posted)] = finish(at, 3600)
    ctx = Ctx(SCOTT)
    run(wars.wars.callback(ctx, 1))
    assert ctx.last.embed.to_dict() == posted.to_dict()


def test_insured_hits_arent_casualties(at, front):
    run(insurance.insurance_buy.callback(Ctx(DAVE)))
    skirmish(at, front)  # Dave's insured for at least 2 minutes: the early hits on him are covered
    war = current(front)
    assert 0 < len(war.acts) - war.casualties <= 4
    [(_, report)] = finish(at, 3600)
    assert f"**Insurance claims:** {len(war.acts) - war.casualties}" in report.fields[3].value


def test_war_titles_come_from_what_happened(at, front):
    for i in range(8):  # Scott and Dave both bad Pat, who never fires back
        at(10 * i)
        bad(SCOTT if i % 2 else DAVE, PAT, front)
    options = dict(wars.title_options(current(front), 1, {"persecuted": "Pat", "aggressor": "Dave"}))
    assert options["The First Great Badening"] == 4 and options["The War to End All Bads"] == 4
    assert "The War to End All Sprays" not in options  # it was all bads
    assert options["The Persecution of Pat"] == 3 and options["The Siege of Pat's Dignity"] == 2
    assert options["The Friday Night Massacre"] == 2 and options["The Incident at 21:42"] == 2
    assert options["The War of Eight Poor Decisions"] == 2 and options["The One-Minute War"] == 2  # 70 seconds
    assert options["The First Conflict of Unspecified Origin"] == 1
    [(_, report)] = finish(at, 3600)
    assert "**Never fired back:** <@3>" in report.fields[3].value


def test_a_mixed_war_isnt_named_after_one_weapon(at, front):
    skirmish(at, front)  # half sprays, half bads
    options = dict(wars.title_options(current(front), 1, {"persecuted": "Scott", "aggressor": "Scott"}))
    assert not any("Great" in title or "End All" in title for title in options)
    assert "The Persecution of Scott" not in options  # Scott fought back


def test_a_new_burst_after_the_ceasefire_is_separate(at, front):
    skirmish(at, front)
    skirmish(at, front, start=3600)  # an hour later: the old one's over even if the loop missed it
    assert len(run(wars.ceasefires(wars.now() + timedelta(hours=1)))) == 2
    assert wars.archived(111) == [1, 2]


def test_the_spray_reaction_counts(at, bot, front):
    for i in range(4):
        at(i)
        payload = types.SimpleNamespace(emoji="💦", user_id=(SCOTT if i % 2 else DAVE).id, channel_id=600,
                                        guild_id=111, message_author_id=PAT.id, member=None)
        run(fun.spray_reaction(payload))
    assert wars.open_war(front.id) is not None


def test_wars_command(at, front):
    ctx = Ctx(SCOTT)
    run(wars.wars.callback(ctx))
    assert ctx.last.content == "📜 The archives are empty. Peace, as far as the committee knows."
    skirmish(at, front)
    run(wars.wars.callback(ctx))
    assert "archives are empty" in ctx.last.content  # Still going: not in the archives yet
    finish(at, 3600)
    spree(at, front, start=7200)
    finish(at, 7200 + 3600)
    run(wars.wars.callback(ctx))
    first, second = wars.get_war(1).title, wars.get_war(2).title
    assert ctx.last.embed.description == (f"`2.` 🪖 **{second}**, 9 Oct 2026 (4 hostilities)\n"
                                          f"`1.` ⚔️ **{first}**, 9 Oct 2026 (8 hostilities)")
    run(wars.wars.callback(ctx, 3))
    assert ctx.last.content == "There's no number 3 in the archives. Only 2 so far."


@pytest.mark.parametrize("n, words", [(7, "Seven"), (20, "Twenty"), (23, "Twenty-Three"), (99, "Ninety-Nine"),
                                      (150, "150")])
def test_number_words(n, words):
    assert wars.number_words(n) == words


def test_names_come_from_discord_when_not_cached(monkeypatch):
    """The bot has no members intent, so names usually aren't cached: they're fetched."""
    async def fetch_member(user_id):
        return types.SimpleNamespace(display_name="Dave")
    guild = types.SimpleNamespace(get_member=lambda user_id: None, fetch_member=fetch_member)
    monkeypatch.setattr(wars.common.bot, "get_guild", lambda guild_id: guild, raising=False)
    assert run(REAL_MEMBER_NAME(111, 2)) == "Dave"
    monkeypatch.setattr(wars.common.bot, "get_guild", lambda guild_id: None, raising=False)
    assert run(REAL_MEMBER_NAME(111, 2)) == "Someone"
