"""Find the page of Mackay's Lost Beauties of the English Language each /deadword is on, so its link opens at it:
python -m ktdi.tools.deadword_pages

Reads the archive.org scan's page-by-page text (its _djvu.xml, downloaded each time, about 6 MB). The dictionary is in
alphabetical order, so every line that starts an entry ("Bever, a drink between meals") is a signpost: the OCR mangles
some, but those fall out of order and are dropped. A dead word is on the page its own entry starts on, if the OCR read
its headword right; if not, on the page of the entry that comes just before it alphabetically (its link shows that
page and the next). If the word isn't in the text of those two pages (Mackay groups some words inside a longer entry,
like the "for-" words in his essay on the prefix), the nearest page a few either side that has it wins. Writes each
word's scan page ("page": 41, the 42nd image, linked as /page/n41) into ktdi/lib/deadwords.json.
"""

import bisect
import json
import re
import sys
import urllib.request
from difflib import SequenceMatcher
from html import unescape
from pathlib import Path

BOOK = "cu31924096224880"
SOURCE_URL = f"https://archive.org/download/{BOOK}/{BOOK}_djvu.xml"
DATA = Path(__file__).resolve().parent.parent / "lib" / "deadwords.json"
FIRST_WORD, LAST_WORD = "Abear", "Ynling"  # The dictionary's first and last entries, as the OCR reads them
ENTRY_RE = re.compile(r"^([A-Z][a-zA-Z'’-]+(?: [a-zA-Z'’-]+)?)[,.]")  # "Bever," or "Barrel fever,"


def key(word: str) -> str:
    """How headwords are compared and sorted: letters only, lower case ("Bell-penny" -> "bellpenny")."""
    return re.sub(r"[^a-z]", "", word.lower())


NEARBY = (-2, 6)  # How far back and on to look for a word that isn't on the page its position says


def page_texts(djvu_xml: str) -> list[list[str]]:
    """Each page's words, as keys, for checking a word is really on it."""
    return [[key(w) for w in re.findall(r"<WORD[^>]*>([^<]*)</WORD>", body)]
            for body in re.findall(r"<OBJECT[^>]*>(.*?)</OBJECT>", djvu_xml, re.S)]


def shows(word: str, texts: list[list[str]], page: int) -> bool:
    """Whether a word's link to this page would show it: it's on the page or the next (they're shown side by side),
    as written or within an OCR slip of it."""
    wanted = key(word)
    nearby = [w for p in (page, page + 1) if 0 <= p < len(texts) for w in texts[p]]
    return wanted in "".join(nearby) or any(SequenceMatcher(None, wanted, w).ratio() >= 0.8 for w in nearby if w)


def line_starts(djvu_xml: str) -> list[tuple[int, str]]:
    """(page, the line's first few words) for every line in the scan, in order. Page 0 is the first image."""
    starts = []
    for page, body in enumerate(re.findall(r"<OBJECT[^>]*>(.*?)</OBJECT>", djvu_xml, re.S)):
        for line in re.findall(r"<LINE>(.*?)</LINE>", body, re.S):
            words = [unescape(w) for w in re.findall(r"<WORD[^>]*>([^<]*)</WORD>", line)]
            if words:
                starts.append((page, " ".join(words[:4])))
    return starts


def signposts(starts: list[tuple[int, str]]) -> list[tuple[str, int]]:
    """(headword key, page) for every line that starts a dictionary entry, keeping only the longest run that stays in
    alphabetical order: a mangled headword ("Hiekery") is usually out of order, so it drops out."""
    first = next(i for i, (_, text) in enumerate(starts) if text.startswith(FIRST_WORD))
    last = max(i for i, (_, text) in enumerate(starts) if text.startswith(LAST_WORD))
    entries = []
    for page, text in starts[first:last + 1]:
        found = ENTRY_RE.match(text)
        if found and key(found.group(1)):
            entries.append((key(found.group(1)), page))
    # The longest run in alphabetical order (patience sorting), so a few OCR mistakes can't drag a word elsewhere.
    tails, tail_index, previous = [], [], [-1] * len(entries)
    for i, (word, _) in enumerate(entries):
        place = bisect.bisect_right(tails, word)
        if place:
            previous[i] = tail_index[place - 1]
        if place == len(tails):
            tails.append(word)
            tail_index.append(i)
        else:
            tails[place], tail_index[place] = word, i
    run, i = [], tail_index[-1] if tail_index else -1
    while i != -1:
        run.append(entries[i])
        i = previous[i]
    return run[::-1]


def page_of(word: str, posts: list[tuple[str, int]]) -> int:
    """The page a headword's entry starts on: its own signpost if the OCR read it right, otherwise the page of the
    signpost just before it alphabetically."""
    wanted = key(word)
    keys = [k for k, _ in posts]
    at = bisect.bisect_left(keys, wanted)
    if at < len(posts) and keys[at] == wanted:
        return posts[at][1]
    return posts[max(at - 1, 0)][1]


def add_pages(words: list[dict], posts: list[tuple[str, int]], texts: list[list[str]] | None = None) -> int:
    """Give each word its page, checked against the pages' text if given. Returns how many are sure (found by their
    own headword, or in the text of the pages their link shows)."""
    keys, sure, previous = {k for k, _ in posts}, 0, None
    back, on = NEARBY
    for entry in words:
        page = page_of(entry["word"], posts)
        if texts and not shows(entry["word"], texts, page):
            # Near where it falls alphabetically, then just after the word before it: words.json is in book order,
            # and a few are sub-entries filed under another word ("All-welder" is under "Welder").
            others = sorted(range(page + back, page + on + 1), key=lambda p: (abs(p - page), p))
            if previous is not None:
                others += range(previous, previous + on + 1)
            found_at = next((p for p in others if shows(entry["word"], texts, p)), None)
            if found_at is not None:
                page = found_at
            elif previous is not None and abs(page - previous) > on:
                page = previous  # Nowhere to be seen, and its spelling puts it far from its neighbours: trust the order
        entry["page"] = page
        found = key(entry["word"]) in keys or bool(texts and shows(entry["word"], texts, page))
        sure += found
        if found:
            previous = page
    return sure


def main() -> None:
    print(f"Downloading {SOURCE_URL} ...")
    with urllib.request.urlopen(SOURCE_URL, timeout=120) as response:
        djvu_xml = response.read().decode("utf-8", errors="replace")
    posts = signposts(line_starts(djvu_xml))
    words = json.loads(DATA.read_text(encoding="utf-8"))
    sure = add_pages(words, posts, page_texts(djvu_xml))
    DATA.write_text(json.dumps(words, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(posts)} entries found in the scan. {sure} of {len(words)} words are on the pages their link shows; "
          "the rest are where they fall alphabetically.")
    if len(posts) < 1000:
        sys.exit(1)  # The scan's text isn't what it was: check before trusting the pages.


if __name__ == "__main__":
    main()
