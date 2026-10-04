"""/books: search and download from a Calibre-Web library.

Private by design: marked extras["private"], so the bot never logs who searched for or downloaded what.
"""

import io

import discord
from discord.ext import commands

from ktdi import config
from ktdi.common import SearchPages, log, send_search_pages
from ktdi.lib import library

HELP_CATEGORY = "🔧 Utilities"
DM_FILE_SIZE_LIMIT = 10 * 1024 * 1024  # Discord's upload limit outside boosted servers.
SEARCH_RESULTS_SHOWN = 15

calibre = (
    library.CalibreWeb(config.CALIBRE_URL, config.CALIBRE_USERNAME, config.CALIBRE_PASSWORD, config.BOOK_FORMATS)
    if config.CALIBRE_URL else None
)
# Books seen in recent searches, so /books download <id> knows their formats and sizes.
recent_books: dict[int, library.Book] = {}


def books_configured() -> bool:
    return calibre is not None


def books_available(guild: discord.Guild | None) -> bool:
    return calibre is not None and guild is not None and guild.id in config.BOOKS_GUILD_IDS


def books_enabled():
    async def predicate(ctx: commands.Context) -> bool:
        if calibre is None:
            raise commands.CheckFailure("The library isn't set up on this bot.")
        if not books_available(ctx.guild):
            raise commands.CheckFailure("The library isn't available in this server.")
        return True
    return commands.check(predicate)


def book_line(book: library.Book) -> str:
    title = discord.utils.escape_markdown(book.title[:80])
    formats = ", ".join(f.name.upper() for f in book.formats)
    return f"`{book.id}` **{title}** — {discord.utils.escape_markdown(book.author_text[:60])} ({formats})"


# "private": never log who used it (see is_private_command). "available": whether it's synced to (and /help shows
# it in) a server. "configured": whether it's synced at all.
@commands.hybrid_group(name="books", description="Search and download books from the library.",
                       invoke_without_command=True,
                       extras={"private": True, "available": books_available, "configured": books_configured})
@books_enabled()
async def books(ctx: commands.Context):
    await ctx.send(
        "Use `/books search <anything>` to find books, then `/books download <title or ID>` to get one.",
        ephemeral=True,
    )


@books.command(name="search", description="Search the library by title, author, series or tag.")
@books_enabled()
async def books_search(ctx: commands.Context, *, query: str):
    await ctx.defer(ephemeral=True)
    try:
        results = await calibre.search(query)
    except library.LibraryError as error:
        log.warning("Library search failed: %s", error.log_text)
        await ctx.send(str(error), ephemeral=True)
        return
    recent_books.update({book.id: book for book in results})
    if not results:
        await ctx.send(f"No books match “{discord.utils.escape_markdown(query)}”.", ephemeral=True)
        return
    count = len(results)
    await send_search_pages(ctx, SearchPages(
        results, title=f"📚 {count} result{'s' if count != 1 else ''} for “{query[:100]}”", line=book_line,
        footer="Get one with /books download <ID or title>.", command="/books search", author_id=ctx.author.id,
        per_page=SEARCH_RESULTS_SHOWN))


async def find_book(query: str) -> library.Book | int | list[library.Book]:
    """A book ID, a single matching book, or a list of candidates if the title is ambiguous."""
    if query.isdigit():
        return recent_books.get(int(query)) or int(query)
    results = await calibre.search(query)
    recent_books.update({book.id: book for book in results})
    exact = [book for book in results if book.title.casefold() == query.casefold()]
    if len(exact) == 1 or len(results) == 1:
        return (exact or results)[0]
    return exact or results


@books.command(name="download", description="Download a book by ID or title. Only you will see it.")
@books_enabled()
async def books_download(ctx: commands.Context, *, book: str):
    await ctx.defer(ephemeral=True)
    # Slash replies can be private; prefix commands can't, so those go by DM instead.
    size_limit = ctx.guild.filesize_limit if ctx.interaction else DM_FILE_SIZE_LIMIT
    try:
        found = await find_book(book.strip())
        if isinstance(found, list):
            if not found:
                await ctx.send(f"No books match “{discord.utils.escape_markdown(book)}”.", ephemeral=True)
            else:
                lines = "\n".join(book_line(b) for b in found[:10])
                await ctx.send(f"Several books match. Download one by its ID:\n{lines}", ephemeral=True)
            return
        if isinstance(found, int):
            download = await calibre.download_by_id(found, size_limit)
            title = download.filename.rsplit(".", 1)[0]
        else:
            download = await calibre.download(found, size_limit)
            title = found.title
    except library.LibraryError as error:
        log.warning("Library download failed: %s", error.log_text)
        await ctx.send(str(error), ephemeral=True)
        return

    # Deliberately anonymous: no user, no title.
    log.info("Library: a book was sent (%s)", library.format_size(len(download.data)))
    message = f"📖 **{discord.utils.escape_markdown(title)}**"
    file = discord.File(io.BytesIO(download.data), filename=download.filename)
    if ctx.interaction:
        await ctx.send(message, file=file, ephemeral=True)
        return
    try:
        await ctx.author.send(message, file=file)
        await ctx.reply("📬 Sent it to your DMs.")
    except discord.Forbidden:
        await ctx.reply("I couldn't DM you. Allow DMs from server members, or use `/books download` instead.")


def help_extras(command: commands.Command) -> tuple[str, list[tuple[str, str, bool]]]:
    parent = command.parent.name if command.parent else None
    if not (command.name == "books" or parent == "books"):
        return "", []
    text = (f"With `/books`, search results and books are only shown to you. With `{config.COMMAND_PREFIX}books`, "
            f"search results post in the channel and books are sent by DM.")
    return "", [("Privacy", text, False)]


async def setup(bot: commands.Bot):
    bot.add_command(books)
