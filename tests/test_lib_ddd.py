"""Content warnings from Does the Dog Die (ktdi.lib.ddd), with a fake site: nothing here touches the internet."""

import pytest

from ktdi.lib import ddd
from tests.fakes import run

ITEMS = [{"id": 1, "name": "Alien", "releaseYear": "2003", "itemType": {"name": "TV Show"}},
         {"id": 2, "name": "Alien", "releaseYear": "1979", "itemType": {"name": "Movie"}},
         {"id": 3, "name": "Alien", "releaseYear": "2019", "itemType": {"name": "Movie"}}]
STATS = [
    {"topic": {"name": "a cat dies", "TopicCategory": {"name": "Animal"}}, "yesSum": 40, "noSum": 2},
    {"topic": {"name": "there are jump scares", "TopicCategory": {"name": "Jump Scares"}}, "yesSum": 90, "noSum": 1},
    {"topic": {"name": "a dog dies", "TopicCategory": {"name": "Animal"}}, "yesSum": 1, "noSum": 80},  # No
    {"topic": {"name": "there's a fake jump scare", "TopicCategory": {"name": "Jump Scares"}}, "yesSum": 2,
     "noSum": 0},  # Too few votes
    {"topic": {"name": "someone is restrained"}, "yesSum": 10, "noSum": 9},  # Just: and no category
]


def fake(items=ITEMS, stats=STATS, status=200):
    asked = []

    async def get(url, key):
        asked.append((url, key))
        if "/dddsearch" in url:
            return status, {"items": items}
        return 200, {"topicItemStats": stats}
    return get, asked


def test_the_film_of_that_year_and_what_most_voters_say_yes_to():
    get, asked = fake()
    found = run(ddd.find("Alien", "1979", "secret", get=get))
    assert found.title == "Alien (1979)" and found.link == "https://www.doesthedogdie.com/media/2"
    assert [w.topic for w in found.warnings] == ["there are jump scares", "a cat dies", "someone is restrained"]
    assert found.warnings[2].category == "Other"
    assert asked[0][0] == "https://www.doesthedogdie.com/dddsearch?q=Alien" and asked[0][1] == "secret"


def test_without_a_year_the_first_film_not_the_tv_show():
    get, _ = fake()
    assert run(ddd.find("Alien", None, "k", get=get)).title == "Alien (1979)"


def test_unknown_film_and_a_round_trip():
    get, _ = fake(items=[])
    assert run(ddd.find("Not a film", None, "k", get=get)) is None
    get, _ = fake()
    found = run(ddd.find("Alien", "1979", "k", get=get))
    assert ddd.Warnings.from_json(found.to_json()) == found


def test_a_refusal_or_a_strange_answer_is_an_error():
    get, _ = fake(status=401)
    with pytest.raises(ValueError):
        run(ddd.find("Alien", None, "bad", get=get))
    get, _ = fake(items="not a list")
    with pytest.raises(ValueError):
        run(ddd.find("Alien", None, "k", get=get))
