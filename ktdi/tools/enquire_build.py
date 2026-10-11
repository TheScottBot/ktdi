"""Build /enquire's hints from Enquire Within Upon Everything (1856, this edition 1890s), from Project Gutenberg:
python -m ktdi.tools.enquire_build

Every hint in the book is a numbered paragraph with a title ("1000. Lighting Candles." and how to). The book's
contents give the number each topic starts at (roughly: the book is famously jumbled). The medical, poisoning,
cosmetic, vermin-killing and chemistry topics are left out whole (their advice would hurt someone who followed it,
and /cure has the remedies), as are the reckoning tables. Of the rest, only the hints in
ktdi/lib/enquire_curation.json are kept (by number and title): the book was read once, and anything racist, cruel,
dangerous or meaningless on its own left out, so it's never in the repo. Writes ktdi/lib/enquire.json. The book is public domain; it's
downloaded each time (about 2 MB).

To add a hint, read it in the book first, then add its number and title to "keep" ("1000. Lighting Candles").
"""

import re

from ktdi.tools import gutenberg

BOOK = 10766
CURATION = gutenberg.curation_file("enquire")
START = "\n1. Choice of Articles of Food."
STOP = "\nINDEX OF ENQUIRIES"
TOPIC = re.compile(r"^([A-Z][A-Z ,:;.'&()-]+?) {3,}(\d+)$", re.M)  # "POISONING, TREATMENT IN CASES OF     1340"
LEFT_OUT = {  # Topics left out whole
    "MEDICAL AND SURGICAL ADVICE", "MINOR COMPLAINTS, COUGH, CRAMP ETC.", "POISONING, TREATMENT IN CASES OF",
    "TOILET REQUISITES, RECEIPTS FOR, ETC.", "DESTRUCTION OF VERMIN, NOXIOUS ANIMALS",
    "MISCELLANEOUS PREPARATIONS: INK, GUM, CEMENT, ETC.", "SANITARY PRECAUTIONS AND REGULATIONS",
    "CHILDREN, REARING AND MANAGEMENT OF", "TABLES OF PERCENTAGES, INTEREST, MARKETING, WAGES",
    "ADULTERATIONS OF FOOD, TESTS FOR",
}


def topics(book: str) -> list[tuple[int, str]]:
    """The contents: (first hint number, topic), in number order. "INDOOR GAMES AND AMUSEMENTS" is "Indoor games and
    amusements"."""
    found = {int(number): name for name, number in TOPIC.findall(book[:book.index(START)])}
    return sorted(found.items())


def topic_of(number: int, contents: list[tuple[int, str]]) -> str:
    return next((name for first, name in reversed(contents) if first <= number), contents[0][1])


def tidy(text: str) -> str:
    """Paragraphs joined up, one per line; anything indented further (a table, a verse) keeps its lines."""
    paragraphs = []
    for block in re.split(r"\n\s*\n", text.strip("\n")):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        indent = min(len(line) - len(line.lstrip()) for line in lines)
        # Indented further, ruled, or in columns ("Ace   King")
        laid_out = (any(len(line) - len(line.lstrip()) > indent for line in lines) or "|" in block
                    or (len(lines) > 1 and all(re.search(r"\S {3,}\S", line) for line in lines)))
        paragraphs.append("\n".join(line.strip() for line in lines) if laid_out else " ".join(l.strip() for l in lines))
    return "\n\n".join(paragraphs)


def entries(book: str) -> list[dict]:
    """Every hint: {"number": 1000, "title": "Lighting Candles", "text": "..."}, but none from the topics left out. A
    title that runs on into its text ("2. Mackerel" / "must be perfectly fresh") is part of the text too."""
    book = book.replace("\r\n", "\n")
    contents = topics(book)
    found = []
    for section in gutenberg.numbered_sections(book[book.index(START) + 1:book.index(STOP)]):
        first, _, rest = section["text"].partition("\n")
        title = " ".join(first.split()).rstrip(".:,")
        text = tidy(rest)
        topic = topic_of(section["number"], contents)
        if not text or topic in LEFT_OUT:
            continue
        # "Mackerel" / "must be perfectly fresh...": one sentence (but "i. Fish." starts a list)
        if rest.strip()[:1].islower() and not re.match(r"[ivxl]+\.\s", rest.strip()):
            text = f"{title} {text[0]}{text[1:]}"
        found.append({"number": section["number"], "title": title, "text": text})
    return found


def key(entry: dict) -> str:
    """How a hint is named on the allowlist: "1000. Lighting Candles" (the book numbers two pairs of hints the same)."""
    return f"{entry['number']}. {entry['title']}"


def main() -> None:
    gutenberg.build_from_allowlist(BOOK, "enquire", entries, key=key)


if __name__ == "__main__":
    main()
