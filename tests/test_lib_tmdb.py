"""Where a film's streaming, from TMDB (ktdi.lib.tmdb), with a fake TMDB: nothing here touches the internet."""

import pytest

from ktdi.lib import tmdb
from tests.fakes import run

ALIEN = {"id": 348, "title": "Alien", "release_date": "1979-05-25"}
PROVIDERS = {"results": {
    "GB": {"link": "https://www.themoviedb.org/movie/348-alien/watch?locale=GB",
           "flatrate": [{"provider_name": "Disney Plus"}, {"provider_name": "Disney Plus"}],
           "ads": [{"provider_name": "ITVX"}],
           "rent": [{"provider_name": "Apple TV"}, {"provider_name": "Amazon Video"}],
           "buy": [{"provider_name": "Apple TV"}, {"provider_name": "Disney Plus"}]},
    "PL": {"link": "https://www.themoviedb.org/movie/348-alien/watch?locale=PL",
           "flatrate": [{"provider_name": "Disney Plus"}]},
    "US": {"rent": [{"provider_name": "Apple TV"}]},
    "FR": {"flatrate": [{"provider_name": "Canal+"}]},
}}


def fake(search=None, providers=PROVIDERS, status=200):
    asked = []

    async def get(url, token):
        asked.append((url, token))
        if "/search/movie" in url:
            return status, {"results": [ALIEN] if search is None else search}
        return 200, providers
    return get, asked


def test_split_year_and_flags():
    assert tmdb.split_year("Alien (1979)") == ("Alien", "1979")
    assert tmdb.split_year("Alien") == ("Alien", None)
    assert tmdb.split_year("Blade Runner 2049") == ("Blade Runner 2049", None)
    assert tmdb.flag("GB") == "🇬🇧" and tmdb.flag("pl") == "🇵🇱" and tmdb.flag("US") == "🇺🇸"


def test_variants_of_a_service_are_one_service():
    for name, clean in [("Amazon Prime Video with Ads", "Amazon Prime Video"),
                        ("Amazon Prime Video Free with Ads", "Amazon Prime Video"),
                        ("AMC+ Amazon Channel", "AMC+"), ("AMC Plus Apple TV channel", "AMC+"),
                        ("Paramount Plus Roku Premium Channel", "Paramount+"), ("Disney Plus", "Disney+"),
                        ("Apple TV Store", "Apple TV Store"), ("Shudder", "Shudder")]:
        assert tmdb.clean_name(name) == clean, name
    there = tmdb.country({"flatrate": [{"provider_name": "Amazon Prime Video"}, {"provider_name": "AMC+"},
                                       {"provider_name": "AMC+ Amazon Channel"}],
                          "ads": [{"provider_name": "Amazon Prime Video with Ads"}]})
    assert there.stream == ["Amazon Prime Video", "AMC+"]


def test_each_country_asked_for_in_one_look_up():
    get, asked = fake()
    found = run(tmdb.find("Alien (1979)", "secret", ("GB", "PL", "US"), get=get))
    assert found.title == "Alien (1979)" and list(found.countries) == ["GB", "PL", "US"]  # Not France: not asked
    uk = found.countries["GB"]
    assert uk.stream == ["Disney+", "ITVX"] and uk.link.endswith("locale=GB")  # Subscription, free, ads; once each
    assert uk.rent == ["Apple TV", "Amazon Video"] and uk.buy == ["Apple TV"]  # Not what's on a service anyway
    assert found.countries["PL"].stream == ["Disney+"]
    us = found.countries["US"]
    assert us.stream == [] and us.rent == ["Apple TV"] and us.link is None
    assert len(asked) == 2  # Every country comes back at once
    assert "year=1979" in asked[0][0] and "region=GB" in asked[0][0] and "secret" not in asked[0][0]
    assert all(token == "secret" for _, token in asked)  # A header, never in the URL


def test_a_country_with_nothing_and_an_unknown_film():
    get, _ = fake()
    assert run(tmdb.find("Alien", "t", ("JP",), get=get)).countries["JP"] == tmdb.Country()
    get, _ = fake(search=[])
    assert run(tmdb.find("Not a real film", "t", get=get)) is None


def test_it_round_trips_through_the_cache():
    get, _ = fake()
    found = run(tmdb.find("Alien", "t", ("GB", "US"), get=get))
    assert tmdb.Providers.from_json(found.to_json()) == found


def test_tmdb_saying_no_is_an_error():
    get, _ = fake(status=401)
    with pytest.raises(ValueError):
        run(tmdb.find("Alien", "bad token", get=get))
