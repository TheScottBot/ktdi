"""Talk to a Calibre-Web server through its OPDS feed: search the library and download books."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import unquote, urljoin

import aiohttp

ATOM = "{http://www.w3.org/2005/Atom}"
ACQUISITION = "http://opds-spec.org/acquisition"
DOWNLOAD_HREF_RE = re.compile(r"/opds/download/(\d+)/([^/]+)/?")

# Stop following "next page" links after this many results, so a huge search can't run forever.
MAX_SEARCH_RESULTS = 500


class LibraryError(Exception):
    """A problem talking to Calibre-Web. The message is safe to show the user who asked.

    private=True means the message names a book, so it mustn't be logged.
    """

    def __init__(self, message: str, private: bool = False):
        super().__init__(message)
        self.private = private

    @property
    def log_text(self) -> str:
        return "(details not logged)" if self.private else str(self)


@dataclass
class BookFormat:
    name: str  # e.g. "epub"
    href: str
    size: int | None  # bytes, if the server said


@dataclass
class Book:
    id: int
    title: str
    authors: list[str]
    tags: list[str]
    formats: list[BookFormat] = field(default_factory=list)

    @property
    def author_text(self) -> str:
        return ", ".join(self.authors) or "Unknown author"


@dataclass
class Download:
    filename: str
    data: bytes


class CalibreWeb:
    def __init__(self, base_url: str, username: str, password: str, preferred_formats: list[str]):
        self.base_url = base_url.rstrip("/") + "/"
        self.auth = aiohttp.BasicAuth(username, password)
        self.preferred_formats = [f.lower() for f in preferred_formats]
        self.timeout = aiohttp.ClientTimeout(total=60)

    def _session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(auth=self.auth, timeout=self.timeout)

    @staticmethod
    def _check(response: aiohttp.ClientResponse) -> None:
        if response.status == 401:
            raise LibraryError("Calibre-Web rejected the bot's login (check the username/password, and that the account can download).")
        if response.status == 404:
            raise LibraryError("Calibre-Web couldn't find that.")
        if response.status >= 400:
            raise LibraryError(f"Calibre-Web returned an error ({response.status}).")

    async def search(self, query: str) -> list[Book]:
        """Search titles, authors, series and tags, following pagination."""
        books: list[Book] = []
        url: str | None = urljoin(self.base_url, "opds/search")
        params: dict | None = {"query": query}
        try:
            async with self._session() as session:
                while url and len(books) < MAX_SEARCH_RESULTS:
                    async with session.get(url, params=params) as response:
                        self._check(response)
                        feed = ET.fromstring(await response.read())
                    books.extend(self._parse_entries(feed))
                    url, params = self._next_page(feed, url), None
        except aiohttp.ClientError as error:
            raise LibraryError(f"Couldn't reach Calibre-Web at {self.base_url} ({type(error).__name__}).") from error
        except ET.ParseError as error:
            raise LibraryError("Calibre-Web sent something that isn't an OPDS feed. Is CALIBRE_URL right?") from error
        return books

    async def download(self, book: Book, size_limit: int) -> Download:
        """Download the book in the most preferred format that fits under size_limit bytes."""
        candidates = self._rank_formats(book)
        if not candidates:
            raise LibraryError(f"**{book.title}** has no downloadable files.", private=True)
        fitting = [f for f in candidates if f.size is None or f.size <= size_limit]
        if not fitting:
            sizes = ", ".join(f"{f.name.upper()} {format_size(f.size)}" for f in candidates)
            raise LibraryError(
                f"**{book.title}** is too big for Discord (limit {format_size(size_limit)}; files: {sizes}).",
                private=True,
            )
        chosen = fitting[0]
        try:
            async with self._session() as session:
                async with session.get(urljoin(self.base_url, chosen.href)) as response:
                    self._check(response)
                    if (response.content_length or 0) > size_limit:
                        raise LibraryError(f"**{book.title}** is too big for Discord (limit {format_size(size_limit)}).", private=True)
                    data = await response.read()
                    filename = _filename_from_header(response.headers.get("Content-Disposition"))
        except aiohttp.ClientError as error:
            raise LibraryError(f"Couldn't download from Calibre-Web at {self.base_url} ({type(error).__name__}).") from error
        if len(data) > size_limit:
            raise LibraryError(f"**{book.title}** is too big for Discord (limit {format_size(size_limit)}).", private=True)
        return Download(filename or _safe_filename(f"{book.title} - {book.author_text}.{chosen.name}"), data)

    async def download_by_id(self, book_id: int, size_limit: int) -> Download:
        """Download a book we don't have search details for, trying each preferred format in turn."""
        too_big = False
        try:
            async with self._session() as session:
                for fmt in self.preferred_formats:
                    url = urljoin(self.base_url, f"opds/download/{book_id}/{fmt}/")
                    async with session.get(url) as response:
                        if response.status == 404:
                            continue  # The book doesn't have this format.
                        self._check(response)
                        if (response.content_length or 0) > size_limit:
                            too_big = True
                            continue
                        data = await response.read()
                        if len(data) > size_limit:
                            too_big = True
                            continue
                        filename = _filename_from_header(response.headers.get("Content-Disposition"))
                        return Download(filename or f"book-{book_id}.{fmt}", data)
        except aiohttp.ClientError as error:
            raise LibraryError(f"Couldn't download from Calibre-Web at {self.base_url} ({type(error).__name__}).") from error
        if too_big:
            raise LibraryError(f"Book {book_id} is too big for Discord (limit {format_size(size_limit)}).", private=True)
        raise LibraryError(
            f"Couldn't find book {book_id} in a format I can send ({', '.join(self.preferred_formats)}).", private=True
        )

    def _rank_formats(self, book: Book) -> list[BookFormat]:
        def rank(fmt: BookFormat) -> int:
            try:
                return self.preferred_formats.index(fmt.name)
            except ValueError:
                return len(self.preferred_formats)
        return sorted(book.formats, key=rank)

    @staticmethod
    def _parse_entries(feed: ET.Element) -> list[Book]:
        books = []
        for entry in feed.findall(f"{ATOM}entry"):
            formats = []
            book_id = None
            for link in entry.findall(f"{ATOM}link"):
                if link.get("rel") != ACQUISITION:
                    continue
                match = DOWNLOAD_HREF_RE.search(link.get("href", ""))
                if not match:
                    continue
                book_id = int(match.group(1))
                length = link.get("length")
                formats.append(BookFormat(match.group(2).lower(), link.get("href"), int(length) if length and length.isdigit() else None))
            if book_id is None:
                continue  # Not a book (e.g. a navigation entry).
            books.append(Book(
                id=book_id,
                title=(entry.findtext(f"{ATOM}title") or "Untitled").strip(),
                authors=[a.findtext(f"{ATOM}name", "").strip() for a in entry.findall(f"{ATOM}author") if a.findtext(f"{ATOM}name")],
                tags=[c.get("term") for c in entry.findall(f"{ATOM}category") if c.get("term")],
                formats=formats,
            ))
        return books

    @staticmethod
    def _next_page(feed: ET.Element, current_url: str) -> str | None:
        for link in feed.findall(f"{ATOM}link"):
            if link.get("rel") == "next" and link.get("href"):
                return urljoin(current_url, link.get("href"))
        return None


def format_size(size: int | None) -> str:
    if size is None:
        return "unknown size"
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{max(size // 1024, 1)} KB"


def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "", name).strip()[:150] or "book"


def _filename_from_header(header: str | None) -> str | None:
    if not header:
        return None
    match = re.search(r"filename\*=UTF-8''([^;]+)", header) or re.search(r'filename="?([^";]+)"?', header)
    return _safe_filename(unquote(match.group(1))) if match else None
