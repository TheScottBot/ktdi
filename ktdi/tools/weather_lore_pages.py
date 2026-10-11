"""Find the page of Inwards' Weather Lore (1893) each /weather saying is on, so its link opens at it:
python -m ktdi.tools.weather_lore_pages

Reads the archive.org scan's page-by-page text (its _djvu.xml, downloaded each time, about 4 MB). A saying is on the
page that has the most of its pairs of consecutive words ("winter fog", "fog will", "will freeze"...), which survive
the OCR's slips far better than whole lines; a saying broken over a page turn counts on the page it starts on. Also
picks each saying's rarest word in the book, for the link to highlight. Writes "page" (0 is the first image, linked as
/page/n0) and "highlight" into ktdi/lib/weather_lore.json.
"""

import json
import re
import sys
import urllib.request
from collections import Counter
from html import unescape
from pathlib import Path

BOOK = "cu31924002969099"
SOURCE_URL = f"https://archive.org/download/{BOOK}/{BOOK}_djvu.xml"
DATA = Path(__file__).resolve().parent.parent / "lib" / "weather_lore.json"
LEAST_PAIRS = 2  # A page needs at least this many of a saying's word pairs to count


def keys(text: str) -> list[str]:
    """Words as they're compared: letters only, lower case."""
    return [w for w in (re.sub(r"[^a-z]", "", word.lower()) for word in text.split()) if w]


def page_words(djvu_xml: str) -> list[list[str]]:
    """Each page's words, in order. Page 0 is the first image."""
    return [keys(" ".join(unescape(w) for w in re.findall(r"<WORD[^>]*>([^<]*)</WORD>", body)))
            for body in re.findall(r"<OBJECT[^>]*>(.*?)</OBJECT>", djvu_xml, re.S)]


def pairs(words: list[str]) -> set[tuple[str, str]]:
    return set(zip(words, words[1:]))


def find_page(saying: str, page_pairs: list[set], own_pairs: list[set], previous: int | None) -> int | None:
    """The page with the most of the saying's word pairs (the page and the first lines of the next count together, so
    a saying that runs over a page turn is found where it starts). Ties go to the page that has more of them itself (a
    saying at the top of a page isn't the previous page's), then to the page nearest the last saying's."""
    wanted = pairs(keys(saying))
    if not wanted:
        return None
    scores = [(len(wanted & page_pairs[p]), len(wanted & own_pairs[p])) for p in range(len(page_pairs))]
    best = max(score for score, _ in scores)
    if best < min(LEAST_PAIRS, len(wanted)):
        return None
    candidates = [p for p, (score, _) in enumerate(scores) if score == best]
    return min(candidates, key=lambda p: (-scores[p][1], abs(p - previous) if previous is not None else 0, p))


def rarest_word(saying: str, pages_with: Counter) -> str | None:
    """The saying's word that's on the fewest pages (ties: the longest), for the link to highlight."""
    # Plain words only: archive.org's search trips on hyphens and apostrophes ("two-and-thirty", "Swithin's").
    words = [w.strip(".,;:!?\"()") for w in saying.replace("/", " ").split()]
    words = [w for w in words if re.fullmatch(r"[A-Za-z]{4,}", w)]
    if not words:
        return None
    return min(words, key=lambda w: (pages_with[w.lower()], -len(w)))


def add_pages(sayings: list[dict], pages: list[list[str]]) -> int:
    """Give each saying its page and a word to highlight. Returns how many were found."""
    own_pairs = [pairs(words) for words in pages]
    page_pairs = [pairs(words + (pages[p + 1][:40] if p + 1 < len(pages) else [])) for p, words in enumerate(pages)]
    pages_with = Counter(word for words in pages for word in set(words))
    found, previous = 0, None
    for saying in sayings:
        page = find_page(saying["text"], page_pairs, own_pairs, previous)
        saying["page"] = page
        saying["highlight"] = rarest_word(saying["text"], pages_with)
        if page is not None:
            found, previous = found + 1, page
    return found


def main() -> None:
    print(f"Downloading {SOURCE_URL} ...")
    with urllib.request.urlopen(SOURCE_URL, timeout=180) as response:
        pages = page_words(response.read().decode("utf-8", errors="replace"))
    sayings = json.loads(DATA.read_text(encoding="utf-8"))
    found = add_pages(sayings, pages)
    DATA.write_text(json.dumps(sayings, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{found} of {len(sayings)} sayings found on a page.")
    missing = [s["text"][:60] for s in sayings if s["page"] is None]
    if missing:
        print("Not found (their links open the book at the start):", *missing, sep="\n  ")
    sys.exit(0 if found > len(sayings) * 0.9 else 1)


if __name__ == "__main__":
    main()
