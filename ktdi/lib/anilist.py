"""Pick a random well-known anime from AniList (https://anilist.co), a free GraphQL API that needs no key."""

import random
from dataclasses import dataclass

import aiohttp

API_URL = "https://graphql.anilist.co"
# Pick from the most popular titles, so they're shows people actually have opinions on.
POPULAR_POOL = 500
QUERY = """
query ($page: Int) {
  Page(page: $page, perPage: 1) {
    media(type: ANIME, sort: POPULARITY_DESC, isAdult: false) { title { english romaji } siteUrl }
  }
}
"""

# Used if AniList can't be reached, so the command still works.
FALLBACK_TITLES = [
    "Attack on Titan", "Death Note", "Fullmetal Alchemist: Brotherhood", "One Punch Man", "Demon Slayer",
    "My Hero Academia", "Jujutsu Kaisen", "Spy x Family", "Cowboy Bebop", "Neon Genesis Evangelion",
    "Steins;Gate", "Hunter x Hunter", "Mob Psycho 100", "Chainsaw Man", "Frieren: Beyond Journey's End",
    "Your Lie in April", "Naruto", "One Piece", "Spirited Away", "Code Geass",
]


@dataclass
class Anime:
    title: str
    url: str | None = None  # AniList page, when it came from AniList


def parse(response: dict) -> Anime | None:
    """Turn an AniList response into an Anime, preferring the English title."""
    media = (((response or {}).get("data") or {}).get("Page") or {}).get("media") or []
    if not media:
        return None
    titles = media[0].get("title") or {}
    title = titles.get("english") or titles.get("romaji")
    return Anime(title, media[0].get("siteUrl")) if title else None


async def random_anime() -> Anime:
    """A random popular anime, or one from the built-in list if AniList is unavailable. Never raises."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            payload = {"query": QUERY, "variables": {"page": random.randint(1, POPULAR_POOL)}}
            async with session.post(API_URL, json=payload) as response:
                if response.status == 200:
                    anime = parse(await response.json())
                    if anime:
                        return anime
    except (aiohttp.ClientError, TimeoutError, ValueError):
        pass
    return Anime(random.choice(FALLBACK_TITLES))
