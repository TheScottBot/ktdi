"""Where a film's streaming, from TMDB (The Movie Database), for /nowplaying. No Discord code.

TMDB's free API says which services have a film in each country, with data from JustWatch: search for the title (and
its year, if it has one: "Alien (1979)"), then ask for that film's watch providers, which come back for every country
at once (so more countries cost nothing). It gives the services' names and one JustWatch page per country, not links
into each service (people add those: /nowplaying set stream:).

It needs a TMDB "API Read Access Token" in TMDB_READ_TOKEN (sent as a header, so it never appears in a URL). TMDB and
JustWatch ask to be credited: the lines it makes say "via JustWatch", and /help nowplaying set credits TMDB.
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
class Country:
    link: str | None = None  # JustWatch's page for the film, there
    stream: list[str] = field(default_factory=list)  # On a subscription, free, or free with ads
    rent: list[str] = field(default_factory=list)
    buy: list[str] = field(default_factory=list)


@dataclass
class Providers:
    title: str  # As TMDB has it, with its year: "Alien (1979)"
    countries: dict[str, Country] = field(default_factory=dict)  # "GB" -> where it's on there, in the order asked

    def to_json(self) -> dict:
        return {"title": self.title, "countries": {code: there.__dict__ for code, there in self.countries.items()}}

    @classmethod
    def from_json(cls, data: dict) -> "Providers":
        """Names are tidied again (clean_name), so a film looked up before a tidying rule changed shows the same."""
        def tidy(names: list[str]) -> list[str]:
            return list(dict.fromkeys(clean_name(name) for name in names))
        countries = {}
        for code, there in data["countries"].items():
            stream = tidy(there["stream"])
            countries[code] = Country(there["link"], stream, [n for n in tidy(there["rent"]) if n not in stream],
                                      [n for n in tidy(there["buy"]) if n not in stream])
        return cls(data["title"], countries)


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


def flag(code: str) -> str:
    """"GB" -> 🇬🇧: the two regional-indicator letters."""
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in code.upper() if "A" <= letter <= "Z")


# What TMDB tacks on to a service's name for another way of getting the same thing ("Amazon Prime Video with Ads",
# "AMC+ Amazon Channel"): taken off, so each service is listed once.
VARIANTS = re.compile(r"\s+(?:free\s+)?with\s+ads$|\s+(?:amazon|apple\s+tv|roku\s+premium)\s+channel$|\s+channel$",
                      re.IGNORECASE)


def clean_name(name: str) -> str:
    """"Amazon Prime Video Free with Ads" -> "Amazon Prime Video"; "AMC Plus Apple TV channel" -> "AMC+";
    "Disney Plus" -> "Disney+"."""
    name = VARIANTS.sub("", name.strip())
    return re.sub(r"\s+Plus$", "+", name, flags=re.IGNORECASE)


def _names(entries: list[dict] | None) -> list[str]:
    return list(dict.fromkeys(clean_name(entry["provider_name"]) for entry in entries or []
                              if entry.get("provider_name")))


def country(there: dict) -> Country:
    stream = _names((there.get("flatrate") or []) + (there.get("free") or []) + (there.get("ads") or []))
    return Country(link=there.get("link"), stream=stream,
                   rent=[n for n in _names(there.get("rent")) if n not in stream],
                   buy=[n for n in _names(there.get("buy")) if n not in stream])


async def find(title: str, token: str, regions: tuple[str, ...] = ("GB",), get: Getter | None = None) -> Providers | None:
    """Where it's on in each of those countries (two-letter codes; the first is the one the search favours), or None
    if TMDB doesn't know the film. Raises aiohttp.ClientError, TimeoutError or ValueError (TMDB said no: a bad token,
    say) for the caller to log."""
    name, year = split_year(title)
    query = {"query": name, "include_adult": "false", "region": regions[0]}
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
    everywhere = watch.get("results") or {}
    return Providers(title=f"{film.get('title') or name}" + (f" ({released})" if released else ""),
                     countries={code: country(everywhere.get(code) or {}) for code in regions})
