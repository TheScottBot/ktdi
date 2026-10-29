"""Where a film's streaming, from TMDB (The Movie Database), for /nowplaying. No Discord code.

TMDB's free API says which services have a film in a country, with data from JustWatch: search for the title (and
its year, if it has one: "Alien (1979)"), then ask for that film's watch providers. It gives the services' names and
one JustWatch page for the film, not links into each service (people add those: /nowplaying set stream:).

It needs a TMDB "API Read Access Token" in TMDB_READ_TOKEN (sent as a header, so it never appears in a URL). TMDB and
JustWatch ask to be credited: the line it makes says "via JustWatch", and /help nowplaying set credits TMDB.
"""

import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from urllib.parse import urlencode

import aiohttp

API = "https://api.themoviedb.org/3"
YEAR_RE = re.compile(r"^(.*?)\s*\((\d{4})\)\s*$")


@dataclass
class Providers:
    title: str  # As TMDB has it, with its year: "Alien (1979)"
    link: str | None  # JustWatch's page for it, in that country (via TMDB)
    stream: list[str] = field(default_factory=list)  # On a subscription, free, or free with ads
    rent: list[str] = field(default_factory=list)
    buy: list[str] = field(default_factory=list)


# (url, token) -> (HTTP status, JSON). Swappable so tests don't touch the internet.
Getter = Callable[[str, str], Awaitable[tuple[int, dict]]]


@asynccontextmanager
async def _reader(get: Getter | None):
    if get is not None:
        yield get
        return
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async def real_get(url: str, token: str) -> tuple[int, dict]:
            async with session.get(url, headers={"Authorization": f"Bearer {token}",
                                                 "Accept": "application/json"}) as response:
                return response.status, (await response.json() if response.status == 200 else {})
        yield real_get


def split_year(title: str) -> tuple[str, str | None]:
    """"Alien (1979)" -> ("Alien", "1979"); "Alien" -> ("Alien", None)."""
    match = YEAR_RE.match(title)
    return (match.group(1), match.group(2)) if match else (title.strip(), None)


def _names(entries: list[dict] | None) -> list[str]:
    return list(dict.fromkeys(entry["provider_name"] for entry in entries or [] if entry.get("provider_name")))


async def find(title: str, token: str, region: str = "GB", get: Getter | None = None) -> Providers | None:
    """Where it's on in that country, or None if TMDB doesn't know the film. Raises aiohttp.ClientError,
    TimeoutError or ValueError (TMDB said no: a bad token, say) for the caller to log."""
    name, year = split_year(title)
    query = {"query": name, "include_adult": "false", "region": region}
    if year:
        query["year"] = year
    async with _reader(get) as reader:
        status, found = await reader(f"{API}/search/movie?{urlencode(query)}", token)
        if status != 200:
            raise ValueError(f"TMDB search said {status}")
        results = found.get("results") or []
        if not results:
            return None
        film = results[0]
        status, watch = await reader(f"{API}/movie/{film['id']}/watch/providers", token)
        if status != 200:
            raise ValueError(f"TMDB watch providers said {status}")
    released = (film.get("release_date") or "")[:4]
    there = (watch.get("results") or {}).get(region) or {}
    stream = _names((there.get("flatrate") or []) + (there.get("free") or []) + (there.get("ads") or []))
    return Providers(title=f"{film.get('title') or name}" + (f" ({released})" if released else ""),
                     link=there.get("link"), stream=stream,
                     rent=[n for n in _names(there.get("rent")) if n not in stream],
                     buy=[n for n in _names(there.get("buy")) if n not in stream])
