"""Build /pseudodoxia's chapters from Sir Thomas Browne's Pseudodoxia Epidemica, or "Vulgar Errors" (1646), from
Project Gutenberg's three-volume Works of Sir Thomas Browne (ed. Charles Sayle, 1904-07):
python -m ktdi.tools.pseudodoxia_build

Browne set out to examine everything his age wrongly believed (that a badger's legs are shorter on one side, that
elephants have no joints, that a kingfisher hung by the beak shows which way the wind blows), a chapter each, opening
with the error and then solemnly taking it apart. Each chapter ("CHAPTER V" / "Of the Badger.") is an entry here, with
its book and number, its side-notes and footnotes taken out. Only the chapters in ktdi/lib/pseudodoxia_curation.json
are kept (as "3.5": book, chapter): the book was read once, and what's 1646 at its worst (the chapters on Jews and on
"the blackness of Negroes", and the like) left out. Writes ktdi/lib/pseudodoxia.json. The books are public domain;
they're downloaded each time (about 2.6 MB).

To add a chapter, read it in the book first, then add its key to "keep".
"""

import json
import re

from ktdi.lib import links, roman
from ktdi.tools import gutenberg

VOLUMES = [39960, 39961, 39962]  # Project Gutenberg: The Works of Sir Thomas Browne, volumes 1 to 3
CURATION = gutenberg.curation_file("pseudodoxia")
ORDINALS = ["FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]
BOOK = re.compile(rf"^\s*THE ({'|'.join(ORDINALS)}) BOOK(?:--.*)?$", re.M)  # Not the contents' "THE FIRST BOOK:"
CHAPTER = re.compile(r"^\s*CHAPTER ([IVXL]+)\.?\s*\n\s*\n((?:.+\n)+?)\s*\n", re.M)  # "CHAPTER V" / "Of the Badger."
NOTE = re.compile(r"\[(?:SN|Sidenote|Illustration):[^\]]*\]", re.S)  # Side-notes from the margins, pictures
FOOTNOTE = re.compile(r"\[(?:\d+|[A-Z])\]")  # "[12]", and the lettered notes of book 7 ("[A]")


def tidy(text: str) -> str:
    """Side-notes and footnotes out (a footnote's own paragraph starts "[1]"), paragraphs on one line each."""
    text = NOTE.sub("", text)
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip() and not FOOTNOTE.match(p.strip())]
    return "\n\n".join(" ".join(FOOTNOTE.sub("", p).split()) for p in paragraphs)


def body(volume: str) -> str:
    """Pseudodoxia's part of a volume: from its first book heading (after Religio Medici, in volume 1) to the end, or
    to Hydriotaphia (in volume 3)."""
    volume = volume.replace("\r\n", "\n")
    start = BOOK.search(volume)
    end = volume.find("\nHYDRIOTAPHIA")
    return volume[start.start() if start else 0:end if end > 0 else gutenberg.end_of(volume)]


def chapters(volume: str, number: int = 0) -> list[dict]:
    """A volume's chapters of Pseudodoxia: {"key": "3.5", "book": 3, "chapter": 5, "title": "Of the Badger", "text":
    ..., "volume": its Gutenberg number, "anchor": words to link to it by (from its first paragraph as the page has
    it)}."""
    text = body(volume)
    books = [(m.start(), ORDINALS.index(m.group(1)) + 1) for m in BOOK.finditer(text)]
    heads = list(CHAPTER.finditer(text))
    found = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        book = next((b for start, b in reversed(books) if start < head.start()), None)
        content = tidy(text[head.end():end])
        if book and content:
            chapter = roman.to_int(head.group(1))
            title = " ".join(head.group(2).split()).rstrip(".")
            first = " ".join(NOTE.sub("", re.split(r"\n\s*\n", text[head.end():end].strip())[0]).split())
            found.append({"key": f"{book}.{chapter}", "book": book, "chapter": chapter, "title": title,
                          "text": content, "volume": number, "anchor": links.fragment_text(first)})
    return found


def build(volumes: dict[int, str], curation: dict) -> dict:
    """The chapters on the allowlist, from {Gutenberg number: the volume's text}."""
    keep = set(curation["keep"])
    return {"chapters": [c for number, volume in volumes.items() for c in chapters(volume, number) if c["key"] in keep]}


def main() -> None:
    volumes = {number: gutenberg.download(number) for number in VOLUMES}
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    data = build(volumes, curation)
    (gutenberg.LIB / "pseudodoxia.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(data['chapters'])} chapters kept.")
    missing = set(curation["keep"]) - {c["key"] for c in data["chapters"]}
    if missing:  # The book's been re-transcribed and a chapter's moved.
        raise SystemExit("In the curation but not found in the book: " + ", ".join(sorted(missing)))


if __name__ == "__main__":
    main()
