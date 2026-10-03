"""Reading a Letterboxd list (ktdi.lib.letterboxd), from sample pages: never the real site."""

import asyncio

import pytest

from ktdi.lib import letterboxd
from ktdi.lib.letterboxd import LetterboxdError

LIST = "https://letterboxd.com/someone/list/halloween/"


def poster(name, slug):
    # Trimmed from a real list page (October 2026): each film is a LazyPoster with its name and link.
    return (f'<li class="posteritem" data-object-name="list"><div class="react-component" '
            f'data-component-class="LazyPoster" data-item-name="{name}" data-item-slug="{slug}" '
            f'data-item-link="/film/{slug}/" data-postered-identifier=\'{{&quot;type&quot;:&quot;film&quot;}}\'>'
            f'<div class="poster film-poster"><img alt="{name}"/></div></div></li>')


def page(films, title="Halloween &amp; More", next_href=None):
    nav = f'<div class="paginate-nextprev"><a class="next" href="{next_href}">Older</a></div>' if next_href else ""
    return (f'<html><head><meta property="og:title" content="{title}"></head><body><ul>'
            + "".join(poster(n, s) for n, s in films) + f"</ul>{nav}</body></html>")


def getter(pages, redirects=None):
    """A fake fetch: url -> page text, or a status number."""
    calls = []

    async def get(url):
        calls.append(url)
        final = (redirects or {}).get(url, url)
        found = pages.get(final, 404)
        return (final, found, "") if isinstance(found, int) else (final, 200, found)
    get.calls = calls
    return get


def fetch(url, get):
    return asyncio.run(letterboxd.fetch_list(url, get))


def test_parse_page():
    parsed = letterboxd.parse_page(page([("Alien (1979)", "alien"), ("As Above, So Below (2014)", "as-above-so-below-2014"),
                                         ("Tom &amp; Jerry (2021)", "tom-and-jerry")]), LIST)
    assert parsed.title == "Halloween & More"
    assert [(f.name, f.link) for f in parsed.films] == [
        ("Alien (1979)", "https://letterboxd.com/film/alien/"),
        ("As Above, So Below (2014)", "https://letterboxd.com/film/as-above-so-below-2014/"),
        ("Tom & Jerry (2021)", "https://letterboxd.com/film/tom-and-jerry/")]
    assert parsed.next_url is None


def test_fetch_follows_pages_in_order():
    pages = {LIST: page([("Alien (1979)", "alien")], next_href="/someone/list/halloween/page/2/"),
             LIST + "page/2/": page([("Braindead (1992)", "braindead-1992"), ("Alien (1979)", "alien")])}
    films = fetch(LIST, getter(pages))
    assert (films.title, films.owner, films.url) == ("Halloween & More", "someone", LIST)
    assert [f.name for f in films.films] == ["Alien (1979)", "Braindead (1992)"]  # no doubles


def test_page_limit():
    pages = {LIST: page([("A (2000)", "a")], next_href=LIST)}  # a page that links to itself forever
    get = getter(pages)
    fetch(LIST, get)
    assert len(get.calls) == letterboxd.MAX_PAGES


@pytest.mark.parametrize("typed, tidy", [
    (LIST, LIST), ("letterboxd.com/someone/list/halloween", LIST), ("<https://www.letterboxd.com/someone/list/halloween/>", LIST),
    ("https://letterboxd.com/someone/list/halloween/page/3/", LIST), ("https://boxd.it/abc1", "https://boxd.it/abc1"),
])
def test_check_url(typed, tidy):
    assert letterboxd.check_url(typed) == tidy


@pytest.mark.parametrize("typed", [
    "https://example.com/someone/list/halloween/", "https://letterboxd.com/film/alien/", "https://letterboxd.com/someone/",
    "http://localhost:8080/someone/list/x/", "https://boxd.it/",
])
def test_only_letterboxd_lists(typed):
    with pytest.raises(LetterboxdError, match="isn't a Letterboxd list"):
        letterboxd.check_url(typed)


def test_short_links_must_land_on_a_list():
    pages = {LIST: page([("Alien (1979)", "alien")])}
    assert fetch("boxd.it/abc1", getter(pages, {"https://boxd.it/abc1": LIST})).owner == "someone"
    with pytest.raises(LetterboxdError, match="isn't a Letterboxd list"):
        fetch("boxd.it/abc2", getter({}, {"https://boxd.it/abc2": "https://letterboxd.com/film/alien/"}))


def test_errors():
    with pytest.raises(LetterboxdError, match="doesn't exist"):
        fetch(LIST, getter({}))
    with pytest.raises(LetterboxdError, match="it said 403"):
        fetch(LIST, getter({LIST: 403}))
    with pytest.raises(LetterboxdError, match="couldn't find any films"):
        fetch(LIST, getter({LIST: page([])}))
