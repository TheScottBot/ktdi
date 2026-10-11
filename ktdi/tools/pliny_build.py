"""Build /pliny's chapters from Pliny the Elder's Natural History (AD 77), in John Bostock and H. T. Riley's
translation (1855), from Project Gutenberg's six volumes: python -m ktdi.tools.pliny_build

Pliny wrote down everything anyone told him: elephants that worship the moon, people with no mouths who live on the
smell of apples, a fish that stops ships. Every book is in short titled chapters ("CHAP. 3. (3.)--THE DOCILITY OF THE
ELEPHANT."), each one an entry here, its footnote marks taken out. Only the chapters in
ktdi/lib/pliny_curation.json are kept (as "VIII.3": book, chapter): the books worth it (the world, man, the animals,
remedies, metals and stones; not the gazetteer, trees or crops) were read once, chapter by chapter, keeping the
gloriously wrong and leaving out anything racist, cruel, or a remedy someone might actually try. Writes
ktdi/lib/pliny.json. The books are public domain; they're downloaded each time (about 9 MB).

To add a chapter, read it in the book first, then add its key to "keep".
"""

import json
import re

from ktdi.lib import links
from ktdi.tools import gutenberg

VOLUMES = [57493, 60230, 59131, 61113, 60688, 62704]  # Project Gutenberg, volumes 1 to 6
CURATION = gutenberg.curation_file("pliny")
BOOK = re.compile(r"^BOOK ([IVXL]+)\.(?:\[\d+\])?\n", re.M)  # "BOOK VIII.", "BOOK VII.[835]" (not the contents)
# "CHAP. 3. (3.)—THE DOCILITY...", and the odd "CHAP 90.—" or "CHAP. 39 (14).—"; a title can run over two lines
CHAPTER = re.compile(r"^CHAP\.?\s*(\d+)\.?\s*(?:\([^)\n]*\)\.?\s*)?[—–-]+\s*(.+?)\n\n", re.M | re.S)
FOOTNOTE = re.compile(r"\[\d+\]")


def tidy(text: str) -> str:
    """Footnote marks out, paragraphs on one line each, separated by a blank line."""
    paragraphs = re.split(r"\n\s*\n", FOOTNOTE.sub("", text).strip())
    return "\n\n".join(" ".join(p.split()) for p in paragraphs if p.strip())


def title_of(heading: str) -> str:
    """"THE DOCILITY OF THE ELEPHANT." is "The docility of the elephant"."""
    heading = " ".join(FOOTNOTE.sub("", heading).split()).rstrip(".")
    return heading[:1].upper() + heading[1:].lower()


def chapters(volume: str, number: int = 0) -> list[dict]:
    """A volume's chapters: {"key": "VIII.3", "book": "VIII", "chapter": 3, "title": "The docility of the elephant",
    "text": "...", "volume": its Gutenberg number, "anchor": words to link to it by}. The anchor is from the text as
    the web page has it, footnote marks and all ("the moon.[1570] It is said"), so a link never spans one. The
    footnotes at the end of the volume are left out."""
    volume = volume.replace("\r\n", "\n")
    body = volume[:volume.index("FOOTNOTES:")] if "FOOTNOTES:" in volume else volume[:gutenberg.end_of(volume)]
    parts = BOOK.split(body)
    found = []
    for book, text in zip(parts[1::2], parts[2::2]):
        heads = list(CHAPTER.finditer(text))
        for i, head in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            raw = text[head.end():end]
            content = tidy(raw)
            if content:
                chapter = int(head.group(1))
                first = " ".join(re.split(r"\n\s*\n", raw.strip())[0].split())
                found.append({"key": f"{book}.{chapter}", "book": book, "chapter": chapter,
                              "title": title_of(head.group(2)), "text": content, "volume": number,
                              "anchor": links.fragment_text(first)})
    return found


def build(volumes: dict[int, str], curation: dict) -> dict:
    """The chapters on the allowlist, from {Gutenberg number: the volume's text}."""
    keep = set(curation["keep"])
    return {"chapters": [c for number, volume in volumes.items() for c in chapters(volume, number) if c["key"] in keep]}


def main() -> None:
    volumes = {number: gutenberg.download(number) for number in VOLUMES}
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    data = build(volumes, curation)
    (gutenberg.LIB / "pliny.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(data['chapters'])} chapters kept.")
    missing = set(curation["keep"]) - {c["key"] for c in data["chapters"]}
    if missing:  # The book's been re-transcribed and a chapter's moved.
        raise SystemExit("In the curation but not found in the book: " + ", ".join(sorted(missing)))


if __name__ == "__main__":
    main()
