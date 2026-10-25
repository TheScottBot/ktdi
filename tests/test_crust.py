"""Crust (/play game:crust): the Changeling and the Household (ktdi.features.crust), on the engine (ktdi.sessions)."""

import types
from datetime import datetime, timedelta, timezone

import pytest

from ktdi import db, sessions
from ktdi.features import crust
from tests.fakes import Channel, Guild, Interaction, User, run

SCOTT, DAVE, PAT, AMY = User(1, "scott"), User(2, "dave"), User(3, "pat"), User(4, "amy")
NOON = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
WORDS = [("Bever", "a drink between meals"), ("Nuncheon", "a light meal at noon"), ("Fuddle", "drink"),
         ("Tiff", "a small draught of liquor"), ("Swizzle", "a mixed drink"), ("Nipperkin", "a small measure"),
         ("Posset", "hot milk curdled with ale"), ("Rumbo", "rum punch")]
CARD = {"id": "drink", "theme": "Drink & drinking",
        "words": [{"word": w, "meaning": m, "source": "Mackay (1874)", "link": "https://example.org/" + w}
                  for w, m in WORDS]}


@pytest.fixture(autouse=True)
def table(monkeypatch, clock, bot):
    monkeypatch.setattr(crust, "CARDS", [CARD])
    clock.set(NOON, sessions)
    bot.add_channel(Channel(500, Guild(111)))
    return clock


def deal(players=(SCOTT, DAVE, PAT, AMY), changeling=PAT, order=None):
    """A game in play, with the Changeling and the order fixed."""
    session = sessions.create(111, 500, crust.GAME, SCOTT.id, "live", [p.id for p in players])
    crust.GAME.deal(session)
    session.state.update(changeling=changeling.id, target=0, order=[p.id for p in (order or players)])
    session.phase = "playing"
    sessions.save(session)
    run(sessions.advanced(session, []))
    return sessions.get(session.id)


def act(user, value):
    session = sessions.get(1)
    answer = Interaction(user, Guild(111))
    run(sessions.answered(answer, 1, session.step, value))
    return answer.last.content


def clues(*words, players=(SCOTT, DAVE, PAT, AMY)):
    for user, word in zip(players, words):
        act(user, word)


def votes(**by):
    for user, suspect in by.items():
        act(next(p for p in (SCOTT, DAVE, PAT, AMY) if p.name == user), str(suspect.id))


# --- The cards ---
def test_the_household_see_the_word_and_the_changeling_doesnt():
    session = deal()
    household = crust.GAME.card(session, SCOTT.id).description
    changeling = crust.GAME.card(session, PAT.id).description
    assert "**Household**" in household and "➡️ **Bever**: a drink between meals" in household
    assert "**Changeling**" in changeling and "➡️" not in changeling and "▫️ **Bever**" in changeling
    assert all(word in changeling for word, _ in WORDS)  # The same eight, with their meanings


# --- Clues ---
def test_clues_go_in_order_and_can_be_a_few_words():
    deal()
    assert crust.GAME.ask(sessions.get(1), DAVE.id) == "Not your turn: it's <@1>'s."
    assert crust.GAME.ask(sessions.get(1), SCOTT.id).max_length == crust.CLUE_LENGTH
    assert "needs a word" in act(SCOTT, "  ...  ")
    assert "Not one of the eight" in act(SCOTT, "bever")
    assert "Not one of the eight" in act(SCOTT, "TIFF")  # Any of them, so nobody learns which is the word
    assert "Not one of the eight" in act(SCOTT, "a quick tiff")  # Anywhere in the clue
    assert act(SCOTT, "thirst") == "Your clue: **thirst**."
    assert sessions.get(1).step == f"clue:{DAVE.id}"
    assert "<@1> *thirst*" in crust.GAME.status(sessions.get(1))


def test_a_clue_of_a_few_words_and_small_words_from_the_eight():
    card = {"words": [{"word": "To Sham Abram"}, {"word": "Rum Ned"}]}
    assert not crust.banned(card, "down to the pub")  # "to" is in "To Sham Abram", but it's only a small word
    assert crust.banned(card, "a rum do") and crust.banned(card, "SHAM")
    deal()
    assert act(SCOTT, "after   a long   day") == "Your clue: **after a long day**."


def test_a_clue_out_of_time_is_silence(table):
    deal()
    table.set(NOON + timedelta(seconds=46), sessions)
    run(sessions.tick(sessions.now()))
    session = sessions.get(1)
    assert session.state["clues"] == {"1": None} and session.step == f"clue:{DAVE.id}"


# --- Votes and the end ---
def test_caught_and_wrong_the_household_score(bot):
    deal()
    clues("thirst", "afternoon", "mug", "pub")
    assert sessions.get(1).step == "vote"
    votes(scott=PAT, dave=PAT, amy=PAT, pat=SCOTT)
    assert sessions.get(1).step == "guess"
    assert crust.GAME.ask(sessions.get(1), SCOTT.id).startswith("The Changeling's guessing")
    act(PAT, "4")  # Swizzle: wrong
    session = sessions.get(1)
    assert session.phase == "done" and session.state["outcome"] == "caught"
    reveal = bot.channels[500].sent[-1].embed
    assert reveal.title == "🏠 The Household found the Changeling!"
    assert "The word was **Bever**: *a drink between meals*." in reveal.description
    assert "**The Changeling guessed:** Swizzle" in reveal.description
    assert crust.GAME.results(session) == {1: (1, True, "household"), 2: (1, True, "household"),
                                           3: (0, False, "changeling"), 4: (1, True, "household")}


def test_caught_but_guessing_right_the_changeling_scores_one():
    deal()
    clues("thirst", "afternoon", "mug", "pub")
    votes(scott=PAT, dave=PAT, amy=PAT, pat=SCOTT)
    act(PAT, "0")
    session = sessions.get(1)
    assert session.state["outcome"] == "guessed" and crust.GAME.results(session)[PAT.id] == (1, True, "changeling")


def test_a_tie_or_the_wrong_person_lets_the_changeling_escape():
    deal()
    clues("thirst", "afternoon", "mug", "pub")
    votes(scott=PAT, dave=AMY, amy=PAT, pat=AMY)  # 2-2
    session = sessions.get(1)
    assert session.state["outcome"] == "escaped" and crust.GAME.results(session)[PAT.id] == (2, True, "changeling")


def test_no_voting_for_yourself():
    deal()
    clues("thirst", "afternoon", "mug", "pub")
    session = sessions.get(1)
    assert str(SCOTT.id) not in [value for _, value in crust.GAME.ask(session, SCOTT.id).choices]


def test_the_move_button_says_what_to_do_and_a_vote_is_a_pick():
    def move_label(session):
        return next(item.item.label for item in sessions.view_for(session).children if item.action == "move")

    assert move_label(deal()) == "Give your clue"
    clues("thirst", "afternoon", "mug", "pub")
    session = sessions.get(1)
    assert move_label(session) == "Vote"
    question = crust.GAME.ask(session, SCOTT.id)
    assert question.kind == "choice" and {value for _, value in question.choices} == {"2", "3", "4"}


def test_the_vote_ends_with_the_votes_in_when_time_runs_out(table):
    deal()
    clues("thirst", "afternoon", "mug", "pub")
    votes(scott=DAVE)
    table.set(NOON + timedelta(minutes=5), sessions)
    run(sessions.tick(sessions.now()))
    assert sessions.get(1).state["outcome"] == "escaped"  # One vote, for Dave: the wrong one


def test_a_server_doesnt_get_the_same_card_twice_running(monkeypatch):
    other = dict(CARD, id="other")
    monkeypatch.setattr(crust, "CARDS", [CARD, other])
    first = deal()
    assert crust.pick_card(111)["id"] != first.state["card"]


def test_the_real_cards():
    import json
    if not crust.DATA.exists():
        pytest.skip("No cards built yet")
    cards = json.loads(crust.DATA.read_text(encoding="utf-8"))["cards"]
    assert len(cards) >= 40 and len({card["id"] for card in cards}) == len(cards)
    for card in cards:
        words = [entry["word"].casefold() for entry in card["words"]]
        assert len(card["words"]) == 8 and len(set(words)) == 8, card["id"]
        for entry in card["words"]:
            assert entry["meaning"] and entry["source"] and entry["link"].startswith("http"), (card["id"], entry)
