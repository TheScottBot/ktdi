"""Links into old books at the exact spot, for /cure, /plant, /vulgartongue, /etiquette and /deadword.

Project Gutenberg books: a link to the book's web page with a text fragment (#:~:text=...), so the browser scrolls to
the passage and highlights it (Chrome, Edge, Safari, and Firefox since 131; any other browser just opens the book).
The fragment is the first few words of the passage, stopping before anything that's typeset differently on the page
(quotes, apostrophes, dashes), so it matches.

archive.org scans: a link to the page (and the next, side by side), with the word searched so it's highlighted.
"""

import re
from urllib.parse import quote

FRAGMENT_WORDS = 10  # Enough to be unique (Culpeper repeats his phrases); few enough to keep matching
MIN_FRAGMENT_WORDS = 4  # Fewer than this ("But", "If at a") matches all over the book
# A word goes in the fragment only if it's plain letters, digits, single hyphens and simple punctuation: no quotes or
# apostrophes (curly on the page, straight in our text), double dashes ("--" in the text, "—" on the page) or brackets.
PLAIN_WORD = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*[,;:.!?]?$")


def fragment_text(passage: str, words: int = FRAGMENT_WORDS, least: int = MIN_FRAGMENT_WORDS) -> str:
    """Words from a passage for a text fragment: the first run of `words` plain words in a row, or failing that the
    longest run (if it's at least `least` words). "" if there's no run long enough to find it by."""
    runs, run = [], []
    for word in passage.replace("…", " ").split():
        if PLAIN_WORD.match(word):
            run.append(word)
            if len(run) == words:
                return " ".join(run).rstrip(",;:")
        else:
            runs.append(run)
            run = []
    runs.append(run)
    longest = max(runs, key=len)
    return " ".join(longest).rstrip(",;:") if len(longest) >= least else ""


def _encode(text: str) -> str:
    # Text fragments give "-", "," and "&" meanings of their own, so they're escaped along with everything else.
    return quote(text, safe="").replace("-", "%2D")


def gutenberg(book: int, passage: str | None = None, least: int = MIN_FRAGMENT_WORDS) -> str:
    """A Gutenberg book's web page, scrolled to the passage if it can be. `least` is the fewest words that will do: a
    passage that starts with a dictionary headword can get away with two ("BENE. Good.")."""
    url = f"https://www.gutenberg.org/cache/epub/{book}/pg{book}-images.html"
    text = fragment_text(passage, least=least) if passage else ""
    return f"{url}#:~:text={_encode(text)}" if text else url


def archive_page(book: str, page: int | None, highlight: str | None = None) -> str:
    """An archive.org scan, open at a page (0 is the first image), two pages at a time, with a word highlighted."""
    url = f"https://archive.org/details/{book}"
    if page is not None:
        url += f"/page/n{page}/mode/2up"
    return f"{url}?q={quote(highlight)}" if highlight else url
