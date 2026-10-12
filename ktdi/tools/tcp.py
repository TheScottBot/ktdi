"""Shared by the tools that build a command's data from an early printed book as the Text Creation Partnership
transcribed it by hand (EEBO-TCP: public domain, CC0; bestiary_build, secrets_build): downloading the TEI XML, reading
it into headed sections and their paragraphs, and keeping the paragraphs a curation file lists.

Text is shown in the book's own spelling, but for the long s (s), the strokes over letters that stand for a missing
m or n ("fro̅", "quē"), and the little raised letters of "yᵉ" and "yᵗ" (the, that). Each paragraph keeps its page in
archive.org's scan of the printed book (the EEBO microfilm: one image per printed page, and each <pb/> in the
transcription is one of them), and a word on that page the scan's OCR has, for archive.org to highlight.

A curation file is {"keep": {"<book>:<section>": {"head": the section's heading (a check that it's still the same
section), "name": what it's looked up by, "also": [other names], "paragraphs": [...]}}}. A section's key is its book
and its place among the book's headed sections, from 0; a paragraph is its number in the section's own text, from 0,
or {"number": 0, "end": "...words"} to keep it only up to those words, and may give its own "name" and "also" (a
section of many herbs), and "title": the number of the paragraph that is its title (the Book of Secrets puts "If thou
wilt make a rayne bowe to appeare." on a line of its own), or the words at the paragraph's start that are (they're
taken off its text). Only what's kept is recorded.
"""

import gzip
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from ktdi.tools import gutenberg

TEI = "{http://www.tei-c.org/ns/1.0}"
TCP = "https://raw.githubusercontent.com/textcreationpartnership/{tcp}/master/{tcp}.xml"
SCAN_TEXT = "https://archive.org/download/{scan}/{scan}_hocr_{part}"

SKIPPED = {"note", "figure", "milestone", "am", "desc", "head", "label", "pb"}  # Margins, pictures, abbreviation marks
GLYPHS = {"char:punc": ".", "char:V": "V", "char:cmbAbbrStroke": "̄", "char:leaf": ""}
STROKE = re.compile(r"(\w)[̃̄](?=[bpm]|\W|$)")  # "reme̅ber", "fro̅": m before b, p, m and at a word's end
RAISED = {"ye": "the", "yt": "that", "yu": "thou", "wt": "with", "wch": "which", "Ye": "The", "Yt": "That"}
# A raised letter the microfilm lost ("y•") is "the"; "that" before a word that starts a clause ("y• he maye"); or
# "thou" before a verb of thou's ("If y• wilt")
CLAUSE = {"the", "a", "an", "he", "she", "it", "they", "thou", "we", "i", "his", "her", "their", "all", "no"}
THOU = re.compile(r"(?:wilt|wolt|shalt|hast|art|mayst|maist|canst|doest|dost|wouldest|shouldest)$", re.I)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def render(element: ET.Element) -> str:
    """An element's text: italics as _italics_ (as Gutenberg books have them, so oldbooks.escape shows them), raised
    letters as part of their word, lines of verse separated by " / ", side-notes and pictures out, an illegible letter
    or word as "…" (and a page the microfilm has twice, not at all)."""
    tag = local(element.tag)
    if tag in SKIPPED:
        inner = ""
    elif tag == "gap":
        inner = "" if element.get("reason") == "duplicate" else "…"
    elif tag == "g":
        inner = GLYPHS.get(element.get("ref"), element.text or "")
    else:
        inner = (element.text or "") + "".join(render(child) for child in element)
    if tag == "hi" and element.get("rend") == "sup":
        inner = "^" + inner  # Marked for tidy, which knows the word it's in
    elif tag == "hi" and inner.strip():
        before, words, after = re.match(r"(\s*)(.*?)(\s*)$", inner.replace("_", ""), re.S).groups()
        inner = f"{before}_{words}_{after}"
    elif tag == "l":
        inner += " / "
    elif tag in {"q", "lg"}:  # No " / " after a quotation's last line
        inner = re.sub(r"\s*/\s*$", " ", inner)
    elif tag == "item":
        inner += "; "
    return inner + (element.tail or "")


def tidy(text: str) -> str:
    """Rendered text as it's shown: the long s, the strokes for m and n and the raised letters spelt out, spaces
    mended."""
    text = unicodedata.normalize("NFD", text.replace("ſ", "s").replace("VV", "W").replace("▪", "."))
    text = STROKE.sub(r"\1m", text)
    text = unicodedata.normalize("NFC", re.sub(r"[̃̄]", "n", text))
    text = re.sub(r"\b([YyWw])\^(\w+)", lambda m: RAISED.get(m[1] + m[2], m[1] + m[2]), text)
    text = re.sub(r"\b([Yy])\^•(?=[\s,]+(\w+))", lambda m: ("T" if m[1] == "Y" else "t") + (
        "hou" if THOU.match(m[2]) else "hat" if m[2].casefold() in CLAUSE else "he"), text)
    text = text.replace("^", "")
    text = " ".join(text.split())
    text = re.sub(r"(?: /)+\s*$|^\s*/ ", "", text)
    text = re.sub(r" / ?([.,;:])", r"\1", text)
    text = re.sub(r"\s+([.,;:?!)])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    return re.sub(r"__", "", text).strip()


def opening(text: str) -> str:
    """A paragraph's big first letters (a drop capital and the letters set beside it) as a word: "AMong", and "WE
    are", are "Among" and "We are". A paragraph mark ("¶ ", "☞ ") at the start goes."""
    text = text.lstrip("¶☞❧ ")
    return re.sub(r"^([A-Z])([A-Z]+)(?=[a-z]|\s+[a-z])", lambda m: m[1] + m[2].lower(), text)


def heading(element: ET.Element) -> str:
    """A section's heading, tidied: "OF THE VNICORNE." is "OF THE VNICORNE"."""
    head = element.find(f"{TEI}head")
    text = "" if head is None else (head.text or "") + "".join(render(child) for child in head)
    return tidy(text.replace("_", "")).strip("❧¶☞ .")


def paragraphs(division: ET.Element) -> list[ET.Element]:
    """A section's own paragraphs: not those of the headed sections inside it (those are sections of their own), nor
    any in its margins or pictures. A part inside it with no heading is still its own text."""
    found = []
    for child in division:
        tag = local(child.tag)
        if tag == "p":
            found.append(child)
        elif tag not in {"div", "note", "figure"} or (tag == "div" and child.find(f"{TEI}head") is None):
            found.extend(paragraphs(child))
    return found


def opening_breaks(paragraph: ET.Element) -> list[ET.Element]:
    """The page breaks at the very start of a paragraph, before its first word (a paragraph that starts a page has
    its <pb/> inside it)."""
    breaks = []
    if (paragraph.text or "").strip():
        return breaks
    for child in paragraph:
        if local(child.tag) == "pb":
            breaks.append(child)
        elif local(child.tag) != "milestone" or "".join(child.itertext()).strip():
            break
        if (child.tail or "").strip():
            break
    return breaks


def sections(xml: str, book: str) -> list[dict]:
    """Every headed section of a book's body, in order: {"key": "beasts:112", "head": "OF THE VNICORNE",
    "paragraphs": [{"text", "page": its image in the scan (0 is the first), "folio": its printed page number}]}."""
    root = ET.fromstring(xml)
    page_of, pages, folio = {}, -1, ""
    for element in root.iter():  # Document order: the last <pb/> before a paragraph is the page it starts on
        if local(element.tag) == "pb":
            pages += 1
            folio = element.get("n", folio)
        elif local(element.tag) == "p":
            breaks = opening_breaks(element)
            opening_folio = next((b.get("n") for b in reversed(breaks) if b.get("n")), folio)
            page_of[id(element)] = (pages + len(breaks) - 1, opening_folio)  # The scan has no image for one page
    body = root.find(f".//{TEI}body")
    headed = [d for d in body.iter(f"{TEI}div") if d.find(f"{TEI}head") is not None]
    return [{"key": f"{book}:{number}", "head": heading(division),
             "paragraphs": [{"text": opening(tidy(render(p))), "page": page_of[id(p)][0], "folio": page_of[id(p)][1]}
                            for p in paragraphs(division)]}
            for number, division in enumerate(headed)]


def highlight(text: str, scanned: str) -> str | None:
    """A word near the start of a passage that the scan's OCR of its page has (so archive.org can highlight it, and
    the passage is easy to find on a crowded page): the first long one, else the longest."""
    scanned = scanned.casefold()
    words = re.findall(r"[A-Za-z]{6,}", text.replace("_", ""))
    on_page = [w for w in words if re.search(rf"\b{w.casefold()}\b", scanned)]
    early = [w for w in on_page[:5] if len(w) >= 8]
    return early[0] if early else max(on_page, key=len, default=None)


def kept(books: dict[str, str], curation: dict, scans: dict[str, list[str] | None] | None = None) -> dict:
    """The paragraphs the curation keeps, from {book: its TCP XML}, with (if `scans` has the book's OCR, a page each)
    a word to highlight. Each is {"key": "beasts:112:3", "name", "also", "head", "book", "folio", "page",
    "highlight", "text"}, and "title" if it has one; "missing" lists anything in the curation that isn't in the book
    (it's been re-transcribed)."""
    found = {section["key"]: section for book, xml in books.items() for section in sections(xml, book)}
    passages, missing = [], []
    for key, section in curation["keep"].items():
        here = found.get(key)
        if not here or here["head"] != section["head"]:
            missing.append(f"{key} ({section['head']})")
            continue
        for item in section["paragraphs"]:
            item = item if isinstance(item, dict) else {"number": item}
            number, end, title = item["number"], item.get("end"), item.get("title")
            text = here["paragraphs"][number]["text"] if number < len(here["paragraphs"]) else ""
            if not text or (end and end not in text) or (isinstance(title, int) and title >= len(here["paragraphs"])) \
                    or (isinstance(title, str) and not text.startswith(title)):
                missing.append(f"{key}:{number}")
                continue
            paragraph = dict(here["paragraphs"][number])
            if end:  # Only the start is kept: the rest of the paragraph wasn't (the Manticore's whelps)
                paragraph["text"] = paragraph["text"][:paragraph["text"].index(end) + len(end)]
            if isinstance(title, str):  # Its first words are its title
                paragraph["text"] = paragraph["text"][len(title):].strip()
            elif title is not None:
                title = here["paragraphs"][title]["text"]
            book = key.split(":")[0]
            ocr = (scans or {}).get(book)
            page_text = ocr[paragraph["page"]] if ocr and 0 <= paragraph["page"] < len(ocr) else ""
            passages.append({"key": f"{key}:{number}", "name": item.get("name", section["name"]),
                             "also": item.get("also", section.get("also", [])), "head": here["head"], "book": book,
                             "folio": paragraph["folio"], "page": paragraph["page"],
                             "highlight": highlight(paragraph["text"], page_text), "text": paragraph["text"],
                             **({"title": title.strip("¶☞ .")} if title else {})})
    return {"passages": passages, "missing": missing}


def fetch(url: str, timeout: int = 120, tries: int = 5) -> bytes:
    print(f"Downloading {url} ...")
    for attempt in range(tries):  # archive.org often 500s, then doesn't
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            problem = error
            if attempt + 1 < tries:
                time.sleep(2 ** attempt)
    raise SystemExit(f"Couldn't download {url}: {problem}")


def download(tcp: str) -> str:
    """A book's TEI XML, by its TCP number ("A13820")."""
    return fetch(TCP.format(tcp=tcp)).decode("utf-8")


def scan_pages(scan: str) -> list[str] | None:
    """The OCR of each image in an archive.org scan, in order; None if archive.org won't give it (the passages are
    built anyway, without words to highlight)."""
    try:
        index = json.loads(gzip.decompress(fetch(SCAN_TEXT.format(scan=scan, part="pageindex.json.gz"))))
        text = gzip.decompress(fetch(SCAN_TEXT.format(scan=scan, part="searchtext.txt.gz"))).decode("utf-8")
    except SystemExit as problem:
        print(f"{problem}\nCarrying on without highlights for that book.")
        return None
    return [text[start:end] for start, end, *_ in index]


def build(name: str, books: dict[str, dict]) -> None:
    """The whole of a build tool: download each book ({book: {"tcp": "A13820", "scan": archive.org identifier}}) and
    its scan's OCR, keep what lib/<name>_curation.json lists, write lib/<name>.json, and stop with an error if
    anything listed wasn't found."""
    texts = {book: download(source["tcp"]) for book, source in books.items()}
    scans = {book: scan_pages(source["scan"]) for book, source in books.items()}
    curation = json.loads(gutenberg.curation_file(name).read_text(encoding="utf-8"))
    data = kept(texts, curation, scans)
    missing = data.pop("missing")
    (gutenberg.LIB / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(data['passages'])} passages kept, from {len(curation['keep'])} sections.")
    if missing:
        raise SystemExit("In the curation but not found in the book: " + ", ".join(missing))
