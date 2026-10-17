"""Build /almanac's days from William Hone's Every-Day Book (1826-27), from Project Gutenberg:
python -m ktdi.tools.almanac_build

The book goes through the year day by day, twice (volume 1, then volume 2): each day ("~January 22.~") has its
saints, then Hone's account of its customs, folklore and anecdotes, a CHRONOLOGY of what happened on it ("1800.--On
the 22d of January, in this year, died George Steevens..."), and in volume 1 a FLORAL DIRECTORY (its flower:
"Early Witlow grass. _Draba verna._"). Each day's saints and flower are kept; of its passages and chronology, only
the ones in ktdi/lib/almanac_curation.json (the book was read once and the best picked, and nothing racist, cruel
or gruesome kept, so it's never in the repo). Writes ktdi/lib/almanac.json. The book is public domain; it's
downloaded each time (about 7 MB).

To add a passage, read it in the book first, then add its key ("1:01-22:3": volume, date, passage number) to "keep".
"""

import json
import re

from ktdi.tools import gutenberg

VOLUMES = {1: 53275, 2: 53276}  # Project Gutenberg books
CURATION = gutenberg.curation_file("almanac")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
# "~January 22.~", and the odd day with a name ("~April 1.--All Fools’ Day.~") or indented
DAY = re.compile(r"^[ \t]*~(" + "|".join(MONTHS) + r") (\d+)\.(?:--(.+?)\.?)?~$", re.M)
SECTION = re.compile(r"^([A-Z][A-Z’' .]+)\.$", re.M)  # "CHRONOLOGY.", "FLORAL DIRECTORY."
MONTH_HEADING = re.compile(r"^(?:" + "|".join(m.upper() for m in MONTHS) + r")(?:, \d{4})?\.$")
SHORTEST, LONGEST = 120, 1400  # A passage worth showing on its own


def tidy(text: str) -> str:
    return " ".join(text.split())


def paragraphs(text: str) -> list[str]:
    """Prose paragraphs: verse, tables, pictures and headings left out, and each on one line."""
    found = []
    for block in re.split(r"\n\s*\n", text):
        stripped = block.strip()
        if (not stripped or block.startswith(" ") or stripped.startswith(("[Illustration", "*", "~"))
                or SECTION.fullmatch(stripped) or MONTH_HEADING.match(stripped)):
            continue
        found.append(tidy(stripped))
    return found


CALENDARS = {"CHRONOLOGY", "FLORAL DIRECTORY", "NATURALISTS’ CALENDAR"}  # The day's regular sections


def saints_of(body: str) -> tuple[str, str]:
    """The day's saints (its first block, if that's names in italics: indented, "  _St. Bademus_, Abbot, A. D. 376.
    _B. Mechtildes_...", or not, "_St. Winwaloe._"), and the rest of the day."""
    body = body.lstrip("\n")
    first, _, rest = body.partition("\n\n")
    names = first.strip().replace("{", " ")
    if "_" in names and len(names) < 600 and (first.startswith("  ") or re.fullmatch(r"(?:_[^_]+_\W*\s*)+", names)):
        return tidy(names), rest
    return "", body


LATIN_NAME = re.compile(r"_[A-ZÆŒ][a-zæœ]+(?: [A-Za-zæœ]|\._)")  # "_Draba verna._", "_Physalis._", "_Æschylus..."


def floral(text: str) -> dict | None:
    """The day's flower from its FLORAL DIRECTORY, {"plant": "Early Witlow grass. _Draba verna._", "for":
    "_St. Vincent._"}: the plant is the line with its Latin name in italics (two words or one, "_Arbutus._", and with
    the book's æ and œ, "_Pæonia Tenuifolia._"), and it's dedicated to the saint on the other line (either way round,
    "Dedicated to" or not). Footnotes ("[349] Brand.") are left out."""
    lines = [tidy(line) for line in text.strip().split("\n") if line.strip() and not line.strip().startswith("[")]
    plant = next((line for line in lines if LATIN_NAME.search(line) and "Dedicated" not in line
                  and not re.match(r"_(?:Sts?|B)\.", line)), None)
    if not plant:
        return None
    devoted = next((line for line in lines if line.startswith("Dedicated") or re.match(r"_(?:Sts?|B)\.", line)), None)
    devoted = re.sub(r"^Dedicated to\s+", "", devoted).rstrip(".") if devoted else None
    return {"plant": plant, "for": devoted}


def day_parts(text: str) -> dict:
    """A day's text split into its saints (the names in italics at the top), its passages (Hone's text, and any
    smaller sections in it, like "THE SEASON."), its chronology, its flower (volume 1) and London's mean
    temperature on it, in °F (volume 2)."""
    sections = SECTION.split(text)
    rest = list(zip(sections[1::2], sections[2::2]))
    saints, body = saints_of(sections[0])
    calendars = {name: text for name, text in rest if name in CALENDARS}
    passages = paragraphs(body) + [p for name, text in rest if name not in CALENDARS for p in paragraphs(text)]
    flower = floral(calendars.get("FLORAL DIRECTORY", ""))
    temperature = re.search(r"Mean Temperature (\d+)·(\d+)", calendars.get("NATURALISTS’ CALENDAR", ""))
    chronology = [p for p in paragraphs(calendars.get("CHRONOLOGY", "")) if re.match(r"\d{3,4}\.", p)]
    return {"saints": saints, "passages": passages, "chronology": chronology, "flower": flower,
            "temperature": float(f"{temperature.group(1)}.{temperature.group(2)}") if temperature else None}


def days(book: str, volume: int) -> list[dict]:
    """Every day in a volume, in order: {"volume": 1, "date": "01-22", "saints", "passages", "chronology",
    "flower"}."""
    book = book.replace("\r\n", "\n")
    body = book[:gutenberg.end_of(book)]
    marks = list(DAY.finditer(body))
    found = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        month = MONTHS.index(mark.group(1)) + 1
        found.append({"volume": volume, "date": f"{month:02d}-{int(mark.group(2)):02d}", "name": mark.group(3),
                      **day_parts(body[mark.end():end])})
    return found


def build(books: dict[int, str], curation: dict) -> dict:
    """Each date of the year ("01-22") with its saints, name ("All Fools’ Day"), flower and London temperature (from
    whichever volume has them), and the passages kept for it, from both volumes."""
    keep = set(curation["keep"])
    dates: dict[str, dict] = {}
    for volume, book in books.items():
        for day in days(book, volume):
            entry = dates.setdefault(day["date"], {"saints": "", "name": None, "flower": None, "temperature": None,
                                                   "passages": []})
            entry["saints"] = entry["saints"] or day["saints"]
            entry["name"] = entry["name"] or day["name"]
            entry["flower"] = entry["flower"] or day["flower"]
            entry["temperature"] = entry["temperature"] or day["temperature"]
            entry["passages"] += [{"volume": volume, "text": re.sub(r"\[\d+\]", "", text)}
                                  for key, text in passage_keys(day) if key in keep]
    return {"days": dict(sorted(dates.items()))}


def main() -> None:
    books = {volume: gutenberg.download(number) for volume, number in VOLUMES.items()}
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    data = build(books, curation)
    (gutenberg.LIB / "almanac.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    kept = sum(len(day["passages"]) for day in data["days"].values())
    print(f"{len(data['days'])} days, {kept} passages kept.")
    found = {key for volume, book in books.items() for day in days(book, volume) for key, _ in passage_keys(day)}
    missing = [key for key in curation["keep"] if key not in found]
    if missing:  # The book's been re-transcribed and a passage has moved.
        raise SystemExit("In the curation but not found in the book: " + ", ".join(missing))


def passage_keys(day: dict) -> list[tuple[str, str]]:
    """Each of a day's passages and chronology items with its key: "1:01-22:3" is volume 1, 22 January, passage 3;
    "1:01-22:c0" is the first chronology item."""
    prefix = f"{day['volume']}:{day['date']}"
    return ([(f"{prefix}:{i}", p) for i, p in enumerate(day["passages"])]
            + [(f"{prefix}:c{i}", p) for i, p in enumerate(day["chronology"])])


if __name__ == "__main__":
    main()
