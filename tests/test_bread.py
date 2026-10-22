"""/bread, How well do you 🍞?: a question a day from the old books, answered privately, with the answer the next
day (ktdi.features.bread, ktdi.tools.bread_build)."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from ktdi import daily, db
from ktdi.features import fun, bread
from ktdi.tools import bread_build
from tests.fakes import Channel, Ctx, Guild, Interaction, User, run

SCOTT, DAVE, PAT = User(1, "scott"), User(2, "dave"), User(3, "pat")
NINE_AM = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)


def question(qid, kind="lostword", answer="A drink between meals", wrong=("A beaver's dam", "A quarrel at cards",
                                                                               "A lazy servant")):
    return {"id": qid, "kind": kind, "question": f"What did the lost word *{qid}* mean?", "answer": answer,
            "wrong": list(wrong), "source": "Mackay, Lost Beauties of the English Language (1874)",
            "link": f"https://example.org/{qid}", "note": f"{qid.title()}: {answer.lower()}."}


@pytest.fixture(autouse=True)
def bank(monkeypatch, clock):
    """Two questions of one kind, and the clock at 9am."""
    monkeypatch.setattr(bread, "QUESTIONS", {q["id"]: q for q in (question("bever"), question("aftertale"))})
    clock.set(NINE_AM, bread)
    return clock


@pytest.fixture
def channel():
    return Channel(500, Guild(111))


def post(channel):
    run(bread.post_bread(channel, None))
    return channel.sent[-1]


def press(choice, user=SCOTT, bake_id=None):
    interaction = Interaction(user)
    run(bread.give_answer(interaction, bake_id or bread.current(111).id, choice))
    return interaction.last


def right_choice():
    return bread.current(111).correct


def wrong_choice():
    return (right_choice() + 1) % 4


# --- The daily bread ---
def test_the_first_post_is_just_a_question_with_four_buttons(channel):
    message = post(channel)
    assert len(message.embeds) == 1
    asked = message.embed
    assert asked.title == "🍞 How well do you bread? No. 1"
    assert asked.description.startswith("**What did the lost word *")
    assert sorted(line[2:] for line in asked.description.split("\n") if line and line[0] in "🇦🇧🇨🇩") == sorted(
        ["A drink between meals", "A beaver's dam", "A quarrel at cards", "A lazy servant"])
    assert "only you see your answer" in asked.description
    assert asked.footer.text == "From Mackay, Lost Beauties of the English Language (1874)"
    bake = bread.current(111)
    assert [item.custom_id for item in message.view.children] == [f"bread:{bake.id}:{n}" for n in range(4)]
    assert bake.message_id == message.id and message.view.timeout is None  # The buttons don't time out


def test_answers_are_private_and_final(channel):
    post(channel)
    reply = press(1)
    assert reply.private and reply.content.startswith("🔒 Locked in: 🇧 *")
    assert "with the next question" in reply.content  # Not set up as a daily post here, so no time to give
    again = press(2)
    assert again.private and again.content.startswith("🍞 You've already answered: 🇧") and "re-kneading" in again.content
    assert [choice for _, choice, _ in bread.answers(bread.current(111))] == [1]


def test_the_next_post_gives_the_answer_then_a_new_question(channel, bank):
    post(channel)
    right = right_choice()
    press(right, SCOTT)
    press(right, PAT)
    press(wrong_choice(), DAVE)
    old = bread.current(111)
    bank.set(NINE_AM + timedelta(days=1), bread)
    message = post(channel)
    answer, asked = message.embeds
    assert answer.title == "🍞 Yesterday's bake: No. 1" and asked.title == "🍞 How well do you bread? No. 2"
    letter = bread.LETTERS[right]
    lines = answer.description.split("\n")
    assert lines[1] == f"It was {letter} **A drink between meals**."
    assert lines[2].startswith("> ") and lines[3].startswith("-# From [Mackay")  # The book's words, and the link
    assert "🍞 for <@1>, <@3>" in answer.description  # The winners get a 🍞
    assert "<@2>" not in answer.description.split("🏆")[0]  # Nobody's told who picked what wrongly...
    counts = next(line for line in lines if line.startswith("🇦 "))
    assert f"{letter} 2" in counts  # ...only how many picked each
    assert "🏆 This week's top bakers: <@1> 1 · <@3> 1" in answer.description
    assert bread.current(111).question_id != old.question_id  # A different question
    late = press(right, DAVE, bake_id=old.id)  # The old post's buttons: closed
    assert "out of the oven" in late.content and late.private


def test_nobody_answering_or_nobody_right(channel, bank):
    post(channel)
    bank.set(NINE_AM + timedelta(days=1), bread)
    answer = post(channel).embeds[0].description
    assert any(line in answer for line in bread.NOBODY_ANSWERED)
    press(wrong_choice())
    bank.set(NINE_AM + timedelta(days=2), bread)
    answer = post(channel).embeds[0].description
    assert any(line in answer for line in bread.NOBODY_RIGHT)


def test_no_question_twice_until_all_have_been_asked(channel, bank):
    asked = []
    for day in range(4):
        bank.set(NINE_AM + timedelta(days=day), bread)
        post(channel)
        asked.append(bread.current(111).question_id)
    assert sorted(asked[:2]) == ["aftertale", "bever"]  # Both, before either again
    assert set(asked[2:]) <= {"aftertale", "bever"}  # Then round again


def test_a_kind_is_picked_before_a_question(monkeypatch):
    many = {f"slang{n}": question(f"slang{n}", kind="slang") for n in range(50)}
    monkeypatch.setattr(bread, "QUESTIONS", {**many, "bever": question("bever")})
    picked = [bread.pick_question(111)["kind"] for _ in range(200)]
    assert 60 < picked.count("lostword") < 140  # About half, not 1 in 51


def test_a_streak_is_mentioned(channel, bank):
    bread.QUESTIONS.update({f"q{n}": question(f"q{n}") for n in range(6)})
    for day in range(4):
        bank.set(NINE_AM + timedelta(days=day), bread)
        message = post(channel)
        if day == 3:
            assert "<@1> (3 in a row)" in message.embeds[0].description
        press(right_choice())
    assert bread.streak(111, SCOTT.id) == 3


def test_a_question_since_taken_out_of_the_bank(channel, monkeypatch):
    post(channel)
    monkeypatch.setattr(bread, "QUESTIONS", {"other": question("other")})
    answer = bread.answer_embed(bread.current(111))
    assert answer.description.startswith("**A question since taken off the menu**")
    assert "It was " in answer.description  # Its answers were stored with it


# --- Scores ---
def test_scores_loaves_and_the_rap_sheet(channel, bank):
    for day in range(2):
        bank.set(NINE_AM + timedelta(days=day), bread)
        post(channel)
        press(right_choice(), SCOTT)
        press(wrong_choice(), DAVE)
    bank.set(NINE_AM + timedelta(days=2), bread)
    post(channel)  # Closes the second: an answer counts once it's out
    assert bread.scores(111) == [(1, 2, 2), (2, 0, 2)]
    assert bread.record(111, SCOTT.id) == (2, 2) and bread.record(111, PAT.id) == (0, 0)
    ctx = Ctx(SCOTT, Guild(111))
    run(bread.bread_scores.callback(ctx))
    assert ctx.last.embed.description.split("\n") == ["1. <@1>: **2** right of 2, crumb, 2 in a row",
                                                      "2. <@2>: **0** right of 2, crumb"]
    sheet = Ctx(SCOTT, Guild(111))
    run(fun.rapsheet.callback(sheet, user=None))
    assert "🍞🍞 from How well do you 🍞? (right 2 of 2)." in sheet.last.text


@pytest.mark.parametrize("right, name", [(0, "Crumb"), (4, "Crumb"), (5, "Crust"), (29, "Bap"), (30, "Bloomer"),
                                         (99, "Cottage loaf"), (100, "Master baker"), (5000, "Master baker")])
def test_loaves(right, name):
    assert bread.loaf(right) == name


@pytest.mark.parametrize("right, shown", [(0, "No 🍞 yet"), (1, "🍞"), (3, "🍞🍞🍞"), (12, "🍞" * 12), (13, "🍞 ×13"),
                                         (2500, "🍞 ×2,500")])
def test_breads_on_the_rap_sheet(right, shown):
    assert bread.breads(right) == shown


def test_scores_follow_the_shared_state(channel, bank):
    post(channel)
    press(right_choice())
    bank.set(NINE_AM + timedelta(days=1), bread)
    post(channel)
    assert bread.record(222, SCOTT.id) == (1, 1)  # Another shared server sees it
    db.set_shared(222, False)
    assert bread.record(222, SCOTT.id) == (0, 0)  # An isolated one doesn't


# --- The commands ---
def test_today_shows_the_question_privately_with_yesterdays_answer(channel, bank):
    ctx = Ctx(SCOTT, Guild(111))
    run(bread.bread.callback(ctx))
    assert "Nothing's in the oven here yet" in ctx.last.content and "/bread setup here" in ctx.last.content
    post(channel)
    run(bread.bread.callback(ctx))
    assert ctx.last.private and [e.title for e in ctx.last.embeds] == ["🍞 How well do you bread? No. 1"]
    assert len(ctx.last.view.children) == 4
    bank.set(NINE_AM + timedelta(days=1), bread)
    post(channel)
    run(bread.bread.callback(ctx))
    assert [e.title for e in ctx.last.embeds] == ["🍞 How well do you bread? No. 2", "🍞 Yesterday's bake: No. 1"]


def test_setting_it_up_posts_the_first_question_straight_away(bank):
    ctx = Ctx(SCOTT, Guild(111), channel=Channel(600, Guild(111)))
    run(bread.bread_setup_here.callback(ctx, time="9am"))
    assert daily.get_setup(111, "bread").channel_id == 600
    assert ctx.channel.sent[-1].embed.title == "🍞 How well do you bread? No. 1"
    assert "Were you cooking? Find out <t:" in press(0).content  # Now it knows when
    run(bread.bread_setup_here.callback(ctx, time="10am"))  # Moving it doesn't start another
    assert len(ctx.channel.sent) == 1


def test_the_buttons_work_after_a_restart():
    """A button's custom_id is all it needs: discord.py rebuilds it from that, whichever post it's on."""
    item = bread.Answer(42, 3)
    assert item.custom_id == "bread:42:3"
    match = bread.Answer.__discord_ui_compiled_template__.fullmatch(item.custom_id)
    rebuilt = run(bread.Answer.from_custom_id(None, item.item, match))
    assert (rebuilt.bake_id, rebuilt.choice) == (42, 3)


# --- The questions ---
def test_the_real_questions(monkeypatch):
    monkeypatch.undo()
    questions = json.loads(bread.DATA.read_text(encoding="utf-8"))["questions"]
    assert len(questions) > 2000 and len({q["id"] for q in questions}) == len(questions)
    assert {"lostword", "slang", "bierce", "phrase", "flower"} <= {q["kind"] for q in questions}
    for q in questions:
        options = [q["answer"], *q["wrong"]]
        assert len(q["wrong"]) == 3 and len({o.lower() for o in options}) == 4, q["id"]
        assert all(0 < len(o) <= 100 for o in options) and q["source"] and q["link"].startswith("http"), q["id"]
        if q["kind"] in ("lostword", "slang", "bierce", "phrase", "flower"):  # Built: checked by word too
            assert not bread_build.LEAVE_OUT_WORDS.search(" ".join([q["question"], *options])), q["id"]


def test_what_was_left_out_stays_out():
    curation = json.loads(bread_build.CURATION.read_text(encoding="utf-8"))
    questions = json.loads(bread.DATA.read_text(encoding="utf-8"))["questions"]
    asked = {q["id"] for q in questions}
    assert not asked & (set(curation["leave_out"]) | set(curation["not_asked"]))
    # A question left out doesn't lend its answer as a wrong one either
    left_out_answers = {a for q in bread_build.from_the_books() if q["id"] in curation["leave_out"]
                        for a in [q["answer"]]}
    offered = {o for q in questions for o in q["wrong"]}
    assert not left_out_answers & offered - {q["answer"] for q in questions}


def test_the_build_is_up_to_date():
    """lib/bread.json is what the build makes from the books and the curation file now."""
    assert bread_build.build()["questions"] == json.loads(bread.DATA.read_text(encoding="utf-8"))["questions"]


@pytest.mark.parametrize("text, sense", [
    ("A cant word for a drink between meals; also a snack.", "A drink between meals"),
    ("Meaning that his luck will save him.", "His luck will save him"),
    ("A conventional lie, such as telling a caller that Mrs. Jones is out.",
     "A conventional lie, such as telling a caller that Mrs. Jones is out"),
])
def test_first_sense(text, sense):
    assert bread_build.first_sense(text) == sense


def test_a_meaning_that_gives_the_word_away_isnt_fair():
    assert not bread_build.fair("Two to one, bar one", "Bar, excepting")
    assert not bread_build.fair("Midnight", "The middle of the night")
    assert bread_build.fair("Like a fish out of water", "Out of place")
    assert not bread_build.fair("Hamcases", "Or HAMCASES Breeches")


# --- !breadsheet: a cryptid, the rap sheet with every last 🍞 ---
def test_the_breadsheet_has_every_bread(monkeypatch):
    monkeypatch.setattr(bread, "record", lambda guild_id, user_id: (2500, 2600) if user_id == SCOTT.id else (3, 4))
    sheet = Ctx(SCOTT, Guild(111))
    run(fun.rapsheet.callback(sheet, user=None))
    assert "🍞 ×2,500 from How well do you 🍞? (right 2500 of 2600)." in sheet.last.content  # The rap sheet: a count
    full = Ctx(SCOTT, Guild(111))
    run(fun.breadsheet.callback(full, user=None))
    messages = [m.content for m in full.sent]
    assert messages[0].startswith("🍞 **Bread sheet: scott**")
    assert "".join(messages).count("🍞") == 2500 + 2  # Every one (and the two in the heading and the line)
    assert len(messages) > 2 and all(fun.message_length(m) <= 2000 for m in messages)  # Over as many as it takes
    dave = Ctx(SCOTT, Guild(111))
    run(fun.breadsheet.callback(dave, user=DAVE))  # Someone else's
    assert dave.last.content.startswith("🍞 **Bread sheet: dave**") and "🍞🍞🍞 from How well" in dave.last.content
    assert fun.breadsheet.extras.get("hidden") and not isinstance(fun.breadsheet, fun.commands.HybridCommand)


def test_long_lines_split_into_messages():
    messages = fun.in_messages(["heading", "🍞" * 2000, "the end"], limit=1000)
    assert messages[0] == "heading" and messages[-1].endswith("the end")
    assert "".join(messages).count("🍞") == 2000 and all(fun.message_length(m) <= 1000 for m in messages)


def test_a_post_that_doesnt_get_through_is_undone(channel, bank, monkeypatch):
    """The network's down at post time: yesterday's question stays open (with its answers), and no new one's opened,
    so when it's tried again nobody's shown the answer to a question they never saw."""
    post(channel)
    press(right_choice(), SCOTT)
    yesterday = bread.current(111)

    async def no_network(*args, **kwargs):
        raise OSError("Temporary failure in name resolution")
    monkeypatch.setattr(channel, "send", no_network)
    bank.set(NINE_AM + timedelta(days=1), bread)
    with pytest.raises(OSError):
        run(bread.post_bread(channel, None))
    assert bread.current(111) == yesterday  # Still open, as it was
    assert db.conn.execute("SELECT COUNT(*) FROM bread_bakes").fetchone()[0] == 1
    assert [right for _, _, right in bread.answers(yesterday)] == [True]
