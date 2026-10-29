"""Where a film's streaming, from TMDB (ktdi.lib.tmdb), with a fake TMDB: nothing here touches the internet."""

import pytest

from ktdi.lib import tmdb
from tests.fakes import run

ALIEN = {"id": 348, "title": "Alien", "release_date": "1979-05-25"}
PROVIDERS = {"results": {"GB": {
    "link": "https://www.themoviedb.org/movie/348-alien/watch?locale=GB",
    "flatrate": [{"provider_name": "Disney Plus"}, {"provider_name": "Disney Plus"}],
    "ads": [{"provider_name": "ITVX"}],
    "rent": [{"provider_name": "Apple TV"}, {"provider_name": "Amazon Video"}],
    "buy": [{"provider_name": "Apple TV"}, {"provider_name": "Disney Plus"}],
}, "US": {"flatrate": [{"provider_name": "Hulu"}]}}}


def fake(search=None, providers=PROVIDERS, status=200):
    asked = []

    async def get(url, token):
        asked.append((url, token))
        if "/search/movie" in url:
            return status, {"results": [ALIEN] if search is None else search}
        return 200, providers
    return get, asked


def test_split_year():
    assert tmdb.split_year("Alien (1979)") == ("Alien", "1979")
    assert tmdb.split_year("Alien") == ("Alien", None)
    assert tmdb.split_year("Blade Runner 2049") == ("Blade Runner 2049", None)


def test_finds_where_its_on_here():
    get, asked = fake()
    found = run(tmdb.find("Alien (1979)", "secret", "GB", get=get))
    assert found.title == "Alien (1979)" and found.link.endswith("locale=GB")
    assert found.stream == ["Disney Plus", "ITVX"]  # Subscription, free and with ads; each once
    assert found.rent == ["Apple TV", "Amazon Video"] and found.buy == ["Apple TV"]  # Not what's on a service anyway
    assert "year=1979" in asked[0][0] and "query=Alien&" in asked[0][0] and "secret" not in asked[0][0]
    assert all(token == "secret" for _, token in asked)  # A header, never in the URL


def test_nothing_here_or_an_unknown_film():
    get, _ = fake(providers={"results": {"US": {"flatrate": [{"provider_name": "Hulu"}]}}})
    found = run(tmdb.find("Alien", "t", "GB", get=get))
    assert found.stream == [] and found.link is None
    get, _ = fake(search=[])
    assert run(tmdb.find("Not a real film", "t", get=get)) is None


def test_tmdb_saying_no_is_an_error():
    get, _ = fake(status=401)
    with pytest.raises(ValueError):
        run(tmdb.find("Alien", "bad token", get=get))
