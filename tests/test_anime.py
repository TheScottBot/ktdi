"""/anime and the AniList client (ktdi.features.anime, ktdi.lib.anilist). No real network calls."""

import pytest

from ktdi import config
from ktdi.features import anime
from ktdi.lib import anilist
from tests.fakes import Ctx, User, run

ASKER = User(1, "scott")


@pytest.fixture
def frieren(monkeypatch):
    async def fake_random_anime():
        return anilist.Anime("Frieren: Beyond Journey's End", "https://anilist.co/anime/154587")
    monkeypatch.setattr(anilist, "random_anime", fake_random_anime)
    monkeypatch.setattr(config, "ANIME_USER_ID", 5)


def test_asks_the_configured_person_and_only_pings_them(frieren):
    ctx = Ctx(ASKER)
    run(anime.anime.callback(ctx))
    reply = ctx.last
    title = "**[Frieren: Beyond Journey's End](<https://anilist.co/anime/154587>)**"
    assert any(line.format(user="<@5>", anime=title) == reply.content for line in anime.ANIME_LINES)
    assert [u.id for u in reply.allowed_mentions.users] == [5]
    assert reply.allowed_mentions.everyone is False and reply.allowed_mentions.roles is False


def test_every_line_names_the_person_and_the_anime():
    for line in anime.ANIME_LINES:
        assert "{user}" in line and "{anime}" in line


def test_not_set_up(monkeypatch):
    monkeypatch.setattr(config, "ANIME_USER_ID", None)
    ctx = Ctx(ASKER)
    run(anime.anime.callback(ctx))
    assert "ANIME_USER_ID" in ctx.last.content and ctx.last.private


def test_title_without_a_link():
    assert anime.anime_text(anilist.Anime("Death Note")) == "**Death Note**"


def test_parse_prefers_english_title():
    response = {"data": {"Page": {"media": [{"title": {"english": "Attack on Titan", "romaji": "Shingeki no Kyojin"},
                                             "siteUrl": "https://anilist.co/anime/16498"}]}}}
    assert anilist.parse(response) == anilist.Anime("Attack on Titan", "https://anilist.co/anime/16498")


def test_parse_falls_back_to_romaji_and_handles_empty():
    only_romaji = {"data": {"Page": {"media": [{"title": {"english": None, "romaji": "Mushishi"}, "siteUrl": "u"}]}}}
    assert anilist.parse(only_romaji).title == "Mushishi"
    assert anilist.parse({"data": {"Page": {"media": []}}}) is None
    assert anilist.parse({}) is None


def test_falls_back_when_anilist_is_unreachable(monkeypatch):
    monkeypatch.setattr(anilist, "API_URL", "http://127.0.0.1:1/graphql")
    picked = run(anilist.random_anime())
    assert picked.title in anilist.FALLBACK_TITLES and picked.url is None
