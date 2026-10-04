"""Reading a public Letterboxd list (/np watchlist import) or film page (/np watchlist add). No Discord code.

Letterboxd has no open API, so this reads the list's web page, the same one anyone can open in a browser. Each film
on it carries data-item-name="Alien (1979)" and data-item-link="/film/alien/"; long lists have a "next" page link.
If Letterboxd changes its pages, parse_page() is the bit to fix (tests/test_lib_letterboxd.py has a sample).
"""

import html
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from urllib.parse import urljoin, urlparse

import aiohttp

SITE = "https://letterboxd.com"
HOSTS = {"letterboxd.com", "www.letterboxd.com"}
SHORT_HOSTS = {"boxd.it"}  # Letterboxd's own short links, which redirect to letterboxd.com.
LIST_PATH_RE = re.compile(r"^/([^/]+)/list/([^/]+)/?(?:page/\d+/?)?$")
FILM_PATH_RE = re.compile(r"^/(?:[^/]+/)?film/([^/]+)(?:/.*)?$")
MAX_PAGES = 10  # Letterboxd shows 100 films a page, so up to 1000.
USER_AGENT = "KTDI Discord bot (reading one public list for a movie night)"

TAG_RE = re.compile(r"<[a-z]+\b[^>]*>", re.IGNORECASE)
ATTR_RE = re.compile(r'([\w-]+)=(?:"([^"]*)"|\'([^\']*)\')')
OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]*)"')


class LetterboxdError(Exception):
    """Something to tell the person who asked."""


@dataclass
class Film:
    name: str  # With the year, as Letterboxd shows it: "Alien (1979)".
    link: str  # https://letterboxd.com/film/alien/


@dataclass
class FilmList:
    title: str
    owner: str
    url: str
    films: list[Film] = field(default_factory=list)


@dataclass
class Page:
    title: str | None
    films: list[Film]
    next_url: str | None


def _attrs(tag: str) -> dict[str, str]:
    return {name: html.unescape(a if a else b) for name, a, b in ATTR_RE.findall(tag)}


def check_url(url: str) -> str:
    """A Letterboxd list URL (or boxd.it short link), tidied; anything else is refused."""
    url = url.strip().strip("<>")
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in SHORT_HOSTS and parsed.path.strip("/"):
        return f"https://boxd.it{parsed.path}"
    match = LIST_PATH_RE.match(parsed.path)
    if host not in HOSTS or not match:
        raise LetterboxdError("That isn't a Letterboxd list. It should look like "
                              "`https://letterboxd.com/someone/list/list-name/`.")
    return f"{SITE}/{match.group(1)}/list/{match.group(2)}/"


def parse_page(page: str, url: str) -> Page:
    films = []
    next_url = None
    for tag in TAG_RE.findall(page):
        attrs = _attrs(tag)
        if "data-item-name" in attrs and "data-item-link" in attrs:
            films.append(Film(attrs["data-item-name"].strip(), urljoin(SITE, attrs["data-item-link"])))
        elif tag.lower().startswith("<a") and "next" in attrs.get("class", "").split() and attrs.get("href"):
            next_url = urljoin(url, attrs["href"])
    title = OG_TITLE_RE.search(page)
    return Page(html.unescape(title.group(1)) if title else None, films, next_url)


# (url) -> (final url after redirects, HTTP status, page text). Swappable so tests don't touch the internet.
Getter = Callable[[str], Awaitable[tuple[str, int, str]]]


@asynccontextmanager
async def _reader(get: Getter | None):
    """The given getter (tests), or a real one for the duration."""
    if get is not None:
        yield get
        return
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT},
                                     timeout=aiohttp.ClientTimeout(total=20)) as session:
        async def real_get(page_url: str) -> tuple[str, int, str]:
            async with session.get(page_url) as response:
                return str(response.url), response.status, await response.text()
        yield real_get


async def _load(get: Getter, url: str, what: str, check: Callable[[str], str] | None = None) -> tuple[str, str]:
    """(where it landed, page text), or a LetterboxdError saying what went wrong with the `what` ("list", "film").
    `check` vets where it landed first, so a short link that lands somewhere else is refused as such."""
    try:
        final_url, status, text = await get(url)
    except (aiohttp.ClientError, TimeoutError) as error:
        raise LetterboxdError("I couldn't reach Letterboxd. Try again in a bit.") from error
    if check:
        final_url = check(final_url)
    if status == 404:
        raise LetterboxdError(f"Letterboxd says that {what} doesn't exist" + (" (or it's private)." if what == "list"
                                                                               else "."))
    if status != 200:
        raise LetterboxdError(f"Letterboxd wouldn't show me that {what} (it said {status}). Try again later.")
    return final_url, text


def looks_like_link(text: str) -> bool:
    """Whether a word someone typed is meant as a link (rather than part of a title)."""
    lowered = text.lower()
    return lowered.startswith(("http://", "https://")) or any(f"{host}/" in lowered for host in HOSTS | SHORT_HOSTS)


def check_film_url(url: str) -> str:
    """A Letterboxd film page (or boxd.it short link), tidied to https://letterboxd.com/film/<slug>/."""
    url = url.strip().strip("<>")
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in SHORT_HOSTS and parsed.path.strip("/"):
        return f"https://boxd.it{parsed.path}"
    match = FILM_PATH_RE.match(parsed.path)  # Also someone's own page for a film: /jenny/film/alien/.
    if host not in HOSTS or not match:
        raise LetterboxdError("That isn't a Letterboxd film. It should look like `https://letterboxd.com/film/alien/`.")
    return f"{SITE}/film/{match.group(1)}/"


async def fetch_film(url: str, get: Getter | None = None) -> Film:
    """A film's name with its year, as Letterboxd shows it ("Nosferatu (1922)"), and its page."""
    url = check_film_url(url)
    async with _reader(get) as get:
        link, text = await _load(get, url, "film", check_film_url)  # A boxd.it link must land on a film.
    title = OG_TITLE_RE.search(text)
    if not title or not title.group(1).strip():
        raise LetterboxdError("I couldn't find the film's name on that page.")
    return Film(html.unescape(title.group(1)).strip(), link)


async def fetch_list(url: str, get: Getter | None = None) -> FilmList:
    url = check_url(url)
    films: list[Film] = []
    seen: set[str] = set()
    title = None
    async with _reader(get) as get:
        page_url: str | None = url
        for _ in range(MAX_PAGES):
            if page_url is None:
                break
            first = page_url == url
            final_url, text = await _load(get, page_url, "list", check_url if first else None)
            if first:
                url = final_url  # Wherever a link (e.g. boxd.it) landed: checked to be a list.
            page = parse_page(text, final_url)
            title = title or page.title
            for film in page.films:
                if film.link not in seen:
                    seen.add(film.link)
                    films.append(film)
            page_url = page.next_url if page.next_url and urlparse(page.next_url).hostname in HOSTS else None
    if not films:
        raise LetterboxdError("I couldn't find any films on that list.")
    owner = LIST_PATH_RE.match(urlparse(url).path).group(1)
    return FilmList(title or "a Letterboxd list", owner, url, films)
