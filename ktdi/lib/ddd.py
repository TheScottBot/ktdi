"""Content warnings for a film, from Does the Dog Die (doesthedogdie.com), for /nowplaying cw. No Discord code.

Does the Dog Die is crowd-sourced: for each film, people vote yes or no on a couple of hundred topics ("a dog dies",
"there are jump scares", "someone is misgendered"). Its free API: search for the title, then ask for that film's
topics with their votes. A topic counts when most voters say yes and enough have voted (YES_MIN).

It needs an API key (DDD_API_KEY, from your profile page on the site), sent as a header. Credit: "via Does the Dog
Die", with a link to the film's page there.
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from urllib.parse import urlencode

import aiohttp

SITE = "https://www.doesthedogdie.com"
YES_MIN = 3  # Votes saying yes before a topic counts (and more yes than no)


@dataclass
class Warning:
    topic: str  # "a dog dies"
    category: str  # "Animal"
    yes: int
    no: int


@dataclass
class Warnings:
    title: str  # As the site has it: "Alien (1979)"
    link: str  # The film's page there
    warnings: list[Warning] = field(default_factory=list)  # The ones that count, most-agreed first

    def to_json(self) -> dict:
        return {"title": self.title, "link": self.link, "warnings": [w.__dict__ for w in self.warnings]}

    @classmethod
    def from_json(cls, data: dict) -> "Warnings":
        return cls(data["title"], data["link"], [Warning(**w) for w in data["warnings"]])


# (url, key) -> (HTTP status, JSON). Swappable so tests don't touch the internet.
Getter = Callable[[str, str], Awaitable[tuple[int, dict]]]


@asynccontextmanager
async def _reader(get: Getter | None):
    if get is not None:
        yield get
        return
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async def real_get(url: str, key: str) -> tuple[int, dict]:
            async with session.get(url, headers={"X-API-KEY": key, "Accept": "application/json"}) as response:
                return response.status, (await response.json(content_type=None) if response.status == 200 else {})
        yield real_get


def pick(items: list[dict], year: str | None) -> dict | None:
    """The film among the search results: a movie, of that year if there's one; else the first movie; else the
    first thing at all."""
    movies = [item for item in items if str((item.get("itemType") or {}).get("name", "")).casefold() == "movie"]
    if year:
        for item in movies:
            if str(item.get("releaseYear") or "")[:4] == year:
                return item
    return (movies or items or [None])[0]


def warnings_from(stats: list[dict]) -> list[Warning]:
    found = []
    for stat in stats or []:
        topic = stat.get("topic") or {}
        yes, no = int(stat.get("yesSum") or 0), int(stat.get("noSum") or 0)
        name = str(topic.get("name") or "").strip()
        if name and yes >= YES_MIN and yes > no:
            found.append(Warning(name, str((topic.get("TopicCategory") or {}).get("name") or "Other"), yes, no))
    return sorted(found, key=lambda w: (-(w.yes / (w.yes + w.no)), -w.yes))


async def find(name: str, year: str | None, key: str, get: Getter | None = None) -> Warnings | None:
    """The film's warnings, or None if the site doesn't know it. Raises aiohttp.ClientError, TimeoutError or
    ValueError (the site said no, or answered in a shape this doesn't know) for the caller to log."""
    async with _reader(get) as reader:
        status, found = await reader(f"{SITE}/dddsearch?{urlencode({'q': name})}", key)
        if status != 200:
            raise ValueError(f"Does the Dog Die's search said {status}")
        if not isinstance(found, dict) or not isinstance(found.get("items", []), list):
            raise ValueError(f"Does the Dog Die's search answered in an unknown shape: {str(found)[:200]}")
        film = pick(found.get("items") or [], year)
        if film is None or "id" not in film:
            return None
        status, media = await reader(f"{SITE}/media/{film['id']}", key)
        if status != 200:
            raise ValueError(f"Does the Dog Die's page for {film['id']} said {status}")
    if not isinstance(media, dict) or not isinstance(media.get("topicItemStats", []), list):
        raise ValueError(f"Does the Dog Die's page answered in an unknown shape: {str(media)[:200]}")
    released = str(film.get("releaseYear") or "")[:4]
    title = str(film.get("name") or name) + (f" ({released})" if released else "")
    return Warnings(title, f"{SITE}/media/{film['id']}", warnings_from(media.get("topicItemStats") or []))
