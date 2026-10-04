"""/rpg against a fake Dropbox: login and token refresh, listing, search, links, privacy, and which servers it shows
in (ktdi.features.rpg, ktdi.lib.dropbox)."""

import asyncio
import logging
import socket
import sys
import types

import pytest
from aiohttp import web
from discord.ext import commands

from ktdi import config
from ktdi.bot import KTDIBot, is_private_command
from ktdi.features import campaigns, rpg
from ktdi.lib import dropbox
from tests.fakes import Ctx, Guild, Interaction, User

PLAYER = User(42, "Washgust")
ROOT = "/Family Room/RPGs"
FILES = ([("D&D 5e/Player's Handbook.pdf", 52_000_000), ("D&D 5e/Dungeon Master's Guide.pdf", 61_000_000),
          ("D&D 5e/Monster Manual.pdf", 70_000_000), ("Call of Cthulhu/Keeper Rulebook.pdf", 90_000_000),
          ("Blades in the Dark.pdf", 15_000_000)]
         + [(f"Zines/Zine {i:02d}.pdf", 1_000_000) for i in range(20)])
PAGE = 10  # Dropbox entries per page, to test following "has_more".


class FakeDropbox:
    """Just enough of Dropbox's API: the token swap, listing a folder, and temporary links."""

    def __init__(self):
        self.tokens_issued = 0
        self.expire_next_call = False
        self.refreshes = []

    def valid(self, request) -> bool:
        return request.headers.get("Authorization") == f"Bearer token-{self.tokens_issued}"

    async def token(self, request):
        form = await request.post()
        self.refreshes.append(form.get("grant_type"))
        if (form.get("refresh_token"), form.get("client_id"), form.get("client_secret")) != ("refresh", "key", "secret"):
            return web.json_response({"error": "invalid_grant"}, status=400)
        self.tokens_issued += 1
        return web.json_response({"access_token": f"token-{self.tokens_issued}", "expires_in": 14400})

    def entries(self):
        folders = [{".tag": "folder", "name": "D&D 5e", "path_display": f"{ROOT}/D&D 5e", "id": "id:folder"}]
        files = [{".tag": "file", "name": p.rsplit("/", 1)[-1], "path_display": f"{ROOT}/{p}", "id": f"id:{n}",
                  "size": size, "is_downloadable": True} for n, (p, size) in enumerate(FILES)]
        return folders + files

    def page(self, start):
        entries = self.entries()
        more = start + PAGE < len(entries)
        return web.json_response({"entries": entries[start:start + PAGE], "cursor": str(start + PAGE), "has_more": more})

    async def list_folder(self, request):
        if self.expire_next_call:
            self.expire_next_call = False
            return web.json_response({"error_summary": "expired_access_token/"}, status=401)
        if not self.valid(request):
            return web.json_response({}, status=401)
        body = await request.json()
        if body["path"] != ROOT or not body["recursive"]:
            return web.json_response({"error_summary": "path/not_found/.."}, status=409)
        return self.page(0)

    async def list_continue(self, request):
        if not self.valid(request):
            return web.json_response({}, status=401)
        return self.page(int((await request.json())["cursor"]))

    async def temporary_link(self, request):
        if not self.valid(request):
            return web.json_response({}, status=401)
        file_id = (await request.json())["path"]
        if not any(e["id"] == file_id for e in self.entries() if e[".tag"] == "file"):
            return web.json_response({"error_summary": "path/not_found/"}, status=409)
        return web.json_response({"link": f"https://dl.example/{file_id}"})


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def dropbox_server(monkeypatch):
    """Runs a fake Dropbox and points /rpg at it. Yields a function that runs a coroutine against it."""
    port, fake = free_port(), FakeDropbox()
    base = f"http://127.0.0.1:{port}"
    client = dropbox.Dropbox("key", "secret", "refresh", ROOT, api=base + "/2/", token_url=base + "/oauth2/token")
    monkeypatch.setattr(rpg, "rulebooks", client)
    monkeypatch.setattr(config, "RPG_GUILD_IDS", [111])

    def run_with_server(coro):
        async def wrapper():
            app = web.Application()
            app.router.add_post("/oauth2/token", fake.token)
            app.router.add_post("/2/files/list_folder", fake.list_folder)
            app.router.add_post("/2/files/list_folder/continue", fake.list_continue)
            app.router.add_post("/2/files/get_temporary_link", fake.temporary_link)
            runner = web.AppRunner(app, access_log=None)
            await runner.setup()
            await web.TCPSite(runner, "127.0.0.1", port).start()
            try:
                return await coro
            finally:
                await runner.cleanup()
        return asyncio.run(wrapper())
    run_with_server.fake, run_with_server.client = fake, client
    return run_with_server


def test_lists_every_file_in_the_folder(dropbox_server):
    files = dropbox_server(rpg.rulebooks.files())
    assert len(files) == len(FILES)  # all pages followed, folders left out
    assert files[0].path == "Blades in the Dark.pdf" and files[0].folder == ""  # sorted by path
    hb = next(f for f in files if f.name == "Player's Handbook.pdf")
    assert (hb.folder, hb.size) == ("D&D 5e", 52_000_000)
    dropbox_server(rpg.rulebooks.files())
    assert dropbox_server.fake.refreshes == ["refresh_token"]  # the listing and token are reused


def test_search_matches_words_in_any_order(dropbox_server):
    names = lambda q: [f.name for f in dropbox_server(rpg.rulebooks.search(q))]  # noqa: E731
    assert names("5e player") == ["Player's Handbook.pdf"]
    assert names("PLAYER 5E") == ["Player's Handbook.pdf"]
    assert names("cthulhu") == ["Keeper Rulebook.pdf"]  # matches the folder
    assert len(names("d&d")) == 3


def test_an_expired_token_is_refreshed(dropbox_server):
    dropbox_server.fake.expire_next_call = True
    assert len(dropbox_server(rpg.rulebooks.files())) == len(FILES)
    assert dropbox_server.fake.refreshes == ["refresh_token", "refresh_token"]


def test_search_command_pages_privately(dropbox_server):
    ctx = Ctx(PLAYER)
    dropbox_server(rpg.rpg_search.callback(ctx, query="zine"))
    pages = ctx.last.view
    assert ctx.last.private and pages.page_count == 2
    embed = pages.embed()
    assert embed.title == "🎲 20 rulebooks for “zine”"
    assert embed.description.splitlines()[0] == "`6` **Zine 00.pdf** — Zines (976 KB)"
    stranger = Interaction(User(99, "stranger"))
    assert asyncio.run(pages.interaction_check(stranger)) is False
    assert "Run your own `/rpg search`" in stranger.last.content

    ctx = Ctx(PLAYER)
    dropbox_server(rpg.rpg_search.callback(ctx, query="5e"))
    # Numbered by place in the whole folder, sorted by path: Blades 1, Call of Cthulhu 2, then D&D 5e.
    assert ctx.last.embed.description.splitlines()[0] == "`3` **Dungeon Master's Guide.pdf** — D&D 5e (58.2 MB)"
    dropbox_server(rpg.rpg_search.callback(ctx, query="tomb of annihilation"))
    assert "No rulebooks match" in ctx.last.content and ctx.last.private


@pytest.mark.parametrize("wanted", ["Player's Handbook", "player's handbook.pdf", "5e player"])
def test_download_by_name(dropbox_server, wanted):
    ctx = Ctx(PLAYER)
    dropbox_server(rpg.rpg_download.callback(ctx, rulebook=wanted))
    assert ctx.last.private
    assert ctx.last.content == ("🎲 **Player's Handbook.pdf** (49.6 MB)\n[Download it](https://dl.example/id:0)\n"
                                "-# The link works for 4 hours.")


def test_download_by_number_and_autocomplete(dropbox_server):
    ctx = Ctx(PLAYER)
    dropbox_server(rpg.rpg_search.callback(ctx, query="cthulhu"))
    number = ctx.last.embed.description.split("`")[1]
    dropbox_server(rpg.rpg_download.callback(ctx, rulebook=number))
    assert "**Keeper Rulebook.pdf**" in ctx.last.content

    interaction = types.SimpleNamespace(guild=Guild(111))
    choices = dropbox_server(rpg.rulebook_autocomplete(interaction, "monster"))
    assert [(c.name, c.value) for c in choices] == [("Monster Manual.pdf — D&D 5e", "id:2")]
    dropbox_server(rpg.rpg_download.callback(ctx, rulebook="id:2"))
    assert "**Monster Manual.pdf**" in ctx.last.content
    assert dropbox_server(rpg.rulebook_autocomplete(types.SimpleNamespace(guild=Guild(222)), "monster")) == []


def test_download_problems(dropbox_server):
    ctx = Ctx(PLAYER)
    dropbox_server(rpg.rpg_download.callback(ctx, rulebook="5e"))
    assert ctx.last.content.startswith("Several rulebooks match. Download one by its number:\n`3` **Dungeon")
    dropbox_server(rpg.rpg_download.callback(ctx, rulebook="tomb of annihilation"))
    assert "No rulebook matches" in ctx.last.content
    dropbox_server(rpg.rpg_download.callback(ctx, rulebook="999"))
    assert "No rulebook matches" in ctx.last.content
    dropbox_server(rpg.rpg_download.callback(ctx, rulebook="id:not-in-the-folder"))
    assert "No rulebook matches" in ctx.last.content  # only files in the folder, whatever's typed


def test_prefix_download_goes_by_dm(dropbox_server):
    player = User(43, "player")
    ctx = Ctx(player, slash=False)
    dropbox_server(rpg.rpg_download.callback(ctx, rulebook="Blades in the Dark"))
    assert "[Download it](https://dl.example/id:4)" in player.dms[0][0]
    assert ctx.last.content == "📬 Sent the link to your DMs."


def test_wrong_folder_and_bad_login(dropbox_server, monkeypatch):
    client = dropbox_server.client
    monkeypatch.setattr(client, "root", "/Family Room/Nope")
    with pytest.raises(dropbox.DropboxError, match="no folder `/Family Room/Nope`"):
        dropbox_server(client.files())
    bad = dropbox.Dropbox("key", "secret", "wrong", ROOT, api=client.api, token_url=client.token_url)
    with pytest.raises(dropbox.DropboxError, match="rejected the bot's login"):
        dropbox_server(bad.files())
    offline = dropbox.Dropbox("key", "secret", "refresh", ROOT, api="http://127.0.0.1:1/2/",
                              token_url="http://127.0.0.1:1/token")
    with pytest.raises(dropbox.DropboxError, match="Couldn't reach Dropbox"):
        asyncio.run(offline.files())


def test_nothing_logged_against_the_player(dropbox_server, caplog):
    caplog.set_level(logging.INFO, logger="ktdi")
    for wanted in ("Player's Handbook", "tomb of annihilation", "5e"):
        dropbox_server(rpg.rpg_download.callback(Ctx(PLAYER), rulebook=wanted))
    dropbox_server(rpg.rpg_search.callback(Ctx(PLAYER), query="cthulhu"))
    logged = "\n".join(caplog.messages)
    for secret in ("Washgust", "Handbook", "annihilation", "cthulhu", "5e"):
        assert secret not in logged
    assert "RPG: a download link was sent (49.6 MB)" in logged


def test_rpg_commands_are_marked_private():
    ctx = Ctx(PLAYER)
    ctx.command = rpg.rpg_download
    assert is_private_command(ctx)


def test_needs_every_setting_including_the_folder():
    # Without RPG_DROPBOX_PATH it would be the whole Dropbox, so it isn't set up at all (the tests have none set).
    assert rpg.rulebooks is None and not rpg.rpg_configured()


def test_only_in_rpg_servers(monkeypatch):
    monkeypatch.setattr(rpg, "rulebooks", dropbox.Dropbox("k", "s", "r", ROOT))
    monkeypatch.setattr(config, "RPG_GUILD_IDS", [111])
    check = rpg.rpg_search.checks[0]
    asyncio.run(check(Ctx(PLAYER, Guild(111))))
    with pytest.raises(commands.CheckFailure, match="isn't available in this server|aren't available in this server"):
        asyncio.run(check(Ctx(PLAYER, Guild(222))))
    monkeypatch.setattr(rpg, "rulebooks", None)
    with pytest.raises(commands.CheckFailure, match="aren't set up"):
        asyncio.run(check(Ctx(PLAYER, Guild(111))))


def test_slash_commands_only_synced_where_they_work(monkeypatch):
    monkeypatch.setattr(campaigns.reminder_loop, "start", lambda: None)
    bot = KTDIBot()
    asyncio.run(bot.load_features())
    assert sorted(bot.unavailable_commands(None)) == ["books", "rpg"]  # neither set up in the tests
    # discord.py loads each feature as a fresh copy of its module: set up the copy the bot is using.
    loaded = sys.modules[bot.get_command("rpg").callback.__module__]
    monkeypatch.setattr(loaded, "rulebooks", dropbox.Dropbox("k", "s", "r", ROOT))
    monkeypatch.setattr(config, "RPG_GUILD_IDS", [111])
    assert bot.unavailable_commands(None) == ["books"]
    assert bot.unavailable_commands(types.SimpleNamespace(id=111)) == ["books"]
    assert sorted(bot.unavailable_commands(types.SimpleNamespace(id=222))) == ["books", "rpg"]
