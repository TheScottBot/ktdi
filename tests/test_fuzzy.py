"""The loose matching behind /cure, /plant, /vulgartongue, /deadword and /etiquette (ktdi.lib.fuzzy)."""

import pytest

from ktdi.lib import fuzzy

THINGS = fuzzy.index([("sore throat", "tickly throat"), ("sore throat", "sore throat"), ("diarrhoea", "diarrhoea"),
                      ("diarrhoea", "the runs"), ("headache", "headache"), ("dance", "dance"), ("nothing", "the my")])


# --- Words ---
def test_words_drop_case_punctuation_and_filler():
    assert fuzzy.words("I've got a really TICKLY throat!") == ["tickly", "throat"]
    assert fuzzy.words("Can’t sleep") == ["cant", "sleep"]
    assert fuzzy.words("the my a") == []


@pytest.mark.parametrize("word, singular", [("daisies", "daisy"), ("boils", "boil"), ("lies", "lie"), ("gas", "ga")])
def test_singular(word, singular):
    assert fuzzy.singular(word) == singular


def test_same_word():
    assert fuzzy.same_word("throat", "throat") and fuzzy.same_word("boils", "boil")
    assert fuzzy.same_word("diarhea", "diarrhoea")  # A typo
    assert not fuzzy.same_word("cat", "cot")  # Short words have to be spelt right
    assert not fuzzy.same_word("throat", "thread")


def test_score():
    assert fuzzy.score(["tickly", "throat"], ["tickly", "throat"]) == 1.0
    assert fuzzy.score(["throat", "tickly"], ["tickly", "throat"]) == 1.0  # Any order
    assert 0 < fuzzy.score(["very", "tickly", "throat"], ["tickly", "throat"]) < 1.0  # A word going spare costs a bit
    assert fuzzy.score(["leg"], ["tickly", "throat"]) == 0.0


# --- Matching ---
def test_index_leaves_out_names_that_are_all_filler():
    assert [name for _, name, _ in THINGS] == ["tickly throat", "sore throat", "diarrhoea", "the runs", "headache",
                                               "dance"]


def test_exact_matches():
    found = fuzzy.best_match("I've got a tickly throat", THINGS)
    assert (found.thing, found.name, found.exact) == ("sore throat", "tickly throat", True)
    assert fuzzy.best_match("the runs", THINGS).exact
    reordered = fuzzy.best_match("my throat is tickly", THINGS)  # Same words, another order: close, not exact
    assert (reordered.name, reordered.exact) == ("tickly throat", False)


def test_close_matches():
    found = fuzzy.best_match("diarhea", THINGS)
    assert (found.thing, found.exact) == ("diarrhoea", False)
    assert fuzzy.best_match("headach", THINGS).thing == "headache"
    assert fuzzy.best_match("a sore throat please", THINGS).thing == "sore throat"


def test_nothing_close():
    for typed in ["xyzzy", "", "   ", "the my"]:
        assert fuzzy.best_match(typed, THINGS) is None


def test_strict_spelling_for_short_look_alike_names():
    assert fuzzy.best_match("dave", THINGS) is not None  # Nearly "dance"...
    assert fuzzy.best_match("dave", THINGS, spelling=fuzzy.STRICT_SPELLING) is None  # ...but not near enough


# --- Autocomplete and searching ---
def test_starting_first():
    names = ["Grinagog", "Bell-penny", "Gag", "Haggle"]
    assert fuzzy.starting_first("g", names) == ["Grinagog", "Gag", "Haggle"]  # Starts with, then contains
    assert fuzzy.starting_first("  GAG ", names) == ["Gag"]
    assert fuzzy.starting_first("g", names, limit=1) == ["Grinagog"]


ENTRIES = [{"w": "Bosky", "text": "Drunk; a little drunk."}, {"w": "Ale", "text": "A drink. Makes people drunk."},
           {"w": "Fuddle", "text": "A drunkard's feast."}, {"w": "Cup", "text": "A vessel."}]


def test_containing_prefers_entries_that_mean_it():
    found = fuzzy.containing("drunk", ENTRIES, lambda e: e["text"])
    assert [e["w"] for e in found] == ["Bosky", "Fuddle"]  # Ale only mentions it in passing
    assert [e["w"] for e in fuzzy.containing("drunk", ENTRIES, lambda e: e["text"], meaning_first=False)] == [
        "Bosky", "Ale", "Fuddle"]
    assert [e["w"] for e in fuzzy.containing("people", ENTRIES, lambda e: e["text"])] == ["Ale"]  # Only in passing
    assert fuzzy.containing("xyzzy", ENTRIES, lambda e: e["text"]) == []
    assert fuzzy.containing("the", ENTRIES, lambda e: e["text"]) == []  # All filler


def test_starting_first_with_any_kind_of_item():
    films = [{"title": "Dial M for Murder"}, {"title": "Alien"}, {"title": "Aliens"}, {"title": "Shrek"}]
    found = fuzzy.starting_first("al", films, key=lambda film: film["title"])
    assert [film["title"] for film in found] == ["Alien", "Aliens", "Dial M for Murder"]


def test_look_up_tries_the_headword_then_uses_then_spelling():
    index = fuzzy.index((e, e["w"]) for e in ENTRIES)
    text = lambda e: e["text"]  # noqa: E731

    def look(typed):
        found = fuzzy.look_up(typed, index, ENTRIES, text)
        return found and (found.kind, [e["w"] for e in found.entries])

    assert look("bosky") == ("exact", ["Bosky"])  # Its own entry, even though "Bosky" isn't in any text
    assert look("drunk") == ("uses", ["Bosky", "Fuddle"])  # Not a headword: the entries that mean it
    assert look("fudle") == ("close", ["Fuddle"])  # Nothing uses it, but it's spelt like one
    assert look("xyzzy") is None


def test_look_up_close_first_prefers_the_nearest_entry_to_its_uses():
    idioms = [{"w": "To rain cats and dogs", "text": "Very heavily."},
              {"w": "Cat and dog life", "text": "Always quarrelling, as cats and dogs do; raining blows."}]
    index = fuzzy.index((e, e["w"]) for e in idioms)
    plain = fuzzy.look_up("raining cats and dogs", index, idioms, lambda e: e["text"])
    assert plain.kind == "uses"  # By default, the entries whose text uses the words
    found = fuzzy.look_up("raining cats and dogs", index, idioms, lambda e: e["text"], close_first=True)
    assert (found.kind, found.entries) == ("close", [idioms[0]])
