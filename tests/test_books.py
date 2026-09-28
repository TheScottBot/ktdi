"""/books against a fake Calibre-Web server: search, paging, downloads, access, and that nothing is logged
against a user (ktdi.features.books, ktdi.lib.library)."""

import asyncio
import base64
import logging
import socket

import pytest
from aiohttp import web
from discord.ext import commands

from ktdi import config
from ktdi.bot import is_private_command
from ktdi.features import books
from ktdi.lib import library
from tests.fakes import Ctx, Guild, Interaction, User

READER = User(42, "Washgust")
BOOKS = [
    (1, "Pride and Prejudice", "Jane Austen", {"epub": 500_000, "pdf": 2_000_000}),
    (2, "Persuasion", "Jane Austen", {"epub": 400_000}),
    (3, "Dune", "Frank Herbert", {"epub": 900_000}),
    (4, "Huge Atlas", "Cartographer", {"pdf": 50_000_000}),
] + [(100 + i, f"Romance Filler {i}", "Various", {"epub": 1000}) for i in range(20)]
PAGE_SIZE = 10


def entry(book):
    book_id, title, author, formats = book
    links = "".join(f'<link rel="http://opds-spec.org/acquisition" href="/opds/download/{book_id}/{fmt}/" length="{size}"/>'
                    for fmt, size in formats.items())
    return f"<entry><title>{title}</title><author><name>{author}</name></author>{links}</entry>"


def authed(request):
    return request.headers.get("Authorization") == "Basic " + base64.b64encode(b"bot:secret").decode()


async def search(request):
    if not authed(request):
        return web.Response(status=401)
    query, offset = request.query.get("query", "").lower(), int(request.query.get("offset", 0))
    matches = [b for b in BOOKS if query in b[1].lower() or query in b[2].lower()]
    page = matches[offset:offset + PAGE_SIZE]
    more = f'<link rel="next" href="/opds/search?query={query}&amp;offset={offset + PAGE_SIZE}"/>' if offset + PAGE_SIZE < len(matches) else ""
    return web.Response(body=f'<feed xmlns="http://www.w3.org/2005/Atom">{more}{"".join(map(entry, page))}</feed>',
                        content_type="application/atom+xml")


async def download(request):
    if not authed(request):
        return web.Response(status=401)
    book = next((b for b in BOOKS if b[0] == int(request.match_info["id"])), None)
    fmt = request.match_info["fmt"]
    if not book or fmt not in book[3]:
        return web.Response(status=404)
    return web.Response(body=b"x" * book[3][fmt],
                        headers={"Content-Disposition": f'attachment; filename="{book[1]} - {book[2]}.{fmt}"'})


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def library_server(monkeypatch):
    """Runs a fake Calibre-Web and points the bot at it. Yields a function that runs a coroutine against it."""
    port = free_port()
    monkeypatch.setattr(books, "calibre", library.CalibreWeb(f"http://127.0.0.1:{port}", "bot", "secret", ["epub", "pdf"]))
    monkeypatch.setattr(config, "BOOKS_GUILD_IDS", [111])

    def run_with_server(coro):
        async def wrapper():
            app = web.Application()
            app.router.add_get("/opds/search", search)
            app.router.add_get("/opds/download/{id}/{fmt}/", download)
            runner = web.AppRunner(app, access_log=None)
            await runner.setup()
            await web.TCPSite(runner, "127.0.0.1", port).start()
            try:
                return await coro
            finally:
                await runner.cleanup()
        return asyncio.run(wrapper())
    return run_with_server


def test_search_follows_pages(library_server):
    results = library_server(books.calibre.search("romance"))
    assert len(results) == 20
    assert library_server(books.calibre.search("austen"))[0].formats[0].size == 500_000


def test_search_results_page_with_buttons(library_server):
    ctx = Ctx(READER)
    library_server(books.books_search.callback(ctx, query="romance"))
    pages = ctx.last.view
    assert ctx.last.private and pages.page_count == 2
    assert pages.previous_page.disabled and not pages.next_page.disabled
    interaction = Interaction(READER)
    asyncio.run(pages.next_page.callback(interaction))
    assert interaction.last.embed.footer.text.startswith("Page 2 of 2")


def test_other_people_cant_turn_the_pages(library_server):
    ctx = Ctx(READER)
    library_server(books.books_search.callback(ctx, query="romance"))
    stranger = Interaction(User(99, "stranger"))
    assert asyncio.run(ctx.last.view.interaction_check(stranger)) is False
    assert "someone else's results" in stranger.last.content


@pytest.mark.parametrize("query, expected", [
    ("Dune", "Dune - Frank Herbert.epub"),     # exact title
    ("1", "Pride and Prejudice - Jane Austen.epub"),  # by ID, EPUB preferred over PDF
])
def test_download_privately(library_server, query, expected):
    ctx = Ctx(READER)
    library_server(books.books_download.callback(ctx, book=query))
    assert ctx.last.file.filename == expected and ctx.last.private


def test_download_problems(library_server):
    ctx = Ctx(READER)
    library_server(books.books_download.callback(ctx, book="austen"))
    assert "Several books match" in ctx.last.content
    library_server(books.books_download.callback(ctx, book="Huge Atlas"))
    assert "too big for Discord" in ctx.last.content
    library_server(books.books_download.callback(ctx, book="zzzz"))
    assert "No books match" in ctx.last.content


def test_prefix_download_goes_by_dm(library_server):
    reader = User(43, "reader")
    ctx = Ctx(reader, slash=False)
    library_server(books.books_download.callback(ctx, book="Persuasion"))
    assert reader.dms[0][1].filename == "Persuasion - Jane Austen.epub"
    assert ctx.last.content == "📬 Sent it to your DMs."


def test_wrong_password_and_server_down():
    bad = library.CalibreWeb("http://127.0.0.1:1", "bot", "wrong", ["epub"])
    with pytest.raises(library.LibraryError, match="Couldn't reach Calibre-Web"):
        asyncio.run(bad.search("x"))


def test_nothing_logged_against_the_reader(library_server, caplog):
    caplog.set_level(logging.INFO, logger="ktdi")
    for query in ("Dune", "Huge Atlas", "zzzz"):
        library_server(books.books_download.callback(Ctx(READER), book=query))
    library_server(books.books_search.callback(Ctx(READER), query="romance"))
    logged = "\n".join(caplog.messages)
    for secret in ("Washgust", "Dune", "Huge Atlas", "zzzz", "romance"):
        assert secret not in logged
    assert "Library: a book was sent" in logged


def test_books_commands_are_marked_private():
    ctx = Ctx(READER)
    ctx.command = books.books_search
    assert is_private_command(ctx)


def test_only_in_library_servers(monkeypatch):
    monkeypatch.setattr(books, "calibre", library.CalibreWeb("http://x", "", "", ["epub"]))
    monkeypatch.setattr(config, "BOOKS_GUILD_IDS", [111])
    check = books.books_search.checks[0]
    asyncio.run(check(Ctx(READER, Guild(111))))
    with pytest.raises(commands.CheckFailure, match="isn't available in this server"):
        asyncio.run(check(Ctx(READER, Guild(222))))
    monkeypatch.setattr(books, "calibre", None)
    with pytest.raises(commands.CheckFailure, match="isn't set up"):
        asyncio.run(check(Ctx(READER, Guild(111))))
