"""Build /herbal's data from the 1531 Tacuini sanitatis on archive.org, in two steps either side of Google Sheets.

    python -m ktdi.tools.herbal_build extract
        Reads archive.org's OCR of the book (ABBYY, which found the tables and their cells), keeps the cells that
        look like words, and writes herbal-build/herbal_cells.csv (with a GOOGLETRANSLATE formula on each row) and
        herbal-build/herbal_cells.json.

    Then: in Google Sheets, File > Import > Upload herbal_cells.csv ("Replace spreadsheet"). Wait until no cell says
    "Loading..." (the worse levels are thousands of translations, so give it a while), then File > Download >
    Comma-separated values.

    python -m ktdi.tools.herbal_build merge
        Finds the downloaded sheet in your Downloads folder (the newest CSV with id, latin and english columns), joins
        the translations (and the worse levels for digging) onto the cells and writes ktdi/lib/herbal.json, which
        /herbal posts from.

The OCR is bad (blackletter, long s read as f...) and machine translation of bad Latin is worse. That's the point.
"""

import csv
import gzip
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

BOOK = "bub_gb_9lIU1a_-ddAC"
ABBYY_URL = f"https://archive.org/download/{BOOK}/{BOOK}_abbyy.gz"
NS = "{http://www.abbyy.com/FineReader_xml/FineReader6-schema-v1.xml}"
ROOT = Path(__file__).resolve().parent.parent.parent
WORK = ROOT / "herbal-build"
OUTPUT = ROOT / "ktdi" / "lib" / "herbal.json"


@dataclass
class Cell:
    id: int
    page: int  # 0-based, as archive.org numbers its page images
    box: tuple[int, int, int, int]  # left, top, right, bottom on the page image
    latin: str


def cell_text(cell: ET.Element) -> tuple[str, tuple[int, int, int, int] | None]:
    """The cell's text, line by line, and the box around it."""
    lines, boxes = [], []
    for line in cell.iter(f"{NS}line"):
        chars = "".join(char.text or "" for char in line.iter(f"{NS}charParams"))
        if chars.strip():
            lines.append(chars.strip())
            boxes.append(tuple(int(line.get(edge)) for edge in "ltrb"))
    if not boxes:
        return "", None
    text = " ".join(lines).replace("�", "")
    text = re.sub(r"(\w)- (\w)", r"\1\2", text)  # rejoin words split across lines
    box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    return re.sub(r"\s+", " ", text).strip(), box


def looks_like_words(text: str) -> bool:
    """Keep "Faciunt infUdonem."; drop row letters, page numbers and "rCP3i*51"-style noise."""
    words = [w for w in re.findall(r"[A-Za-z]{3,}", text)]
    letters = sum(c.isalpha() for c in text)
    return len(words) >= 2 and letters >= 8 and letters / max(len(text.replace(" ", "")), 1) >= 0.7


def extract_cells(abbyy_xml: bytes) -> list[Cell]:
    cells, seen = [], set()
    root = ET.fromstring(abbyy_xml)
    for page_number, page in enumerate(root.iter(f"{NS}page")):
        for block in page.iter(f"{NS}block"):
            if block.get("blockType") != "Table":
                continue
            for cell in block.iter(f"{NS}cell"):
                text, box = cell_text(cell)
                if box and looks_like_words(text) and text.casefold() not in seen:
                    seen.add(text.casefold())
                    cells.append(Cell(len(cells) + 1, page_number, box, text))
    return cells


# The dig: each level round-trips the level above it through one more language, so it gets worse as you go down.
WORSE = [("worse1", "ja"), ("worse2", "zu"), ("worse3", "fi"), ("worse4", "ko")]


def write_sheet(cells: list[Cell], path: Path) -> None:
    """A CSV that Google Sheets imports with the translation formulas on every row: Latin to English, then each
    worse level is the one before it, there and back again through another language."""
    columns = ["id", "latin", "english", *(name for name, _ in WORSE)]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        for row, cell in enumerate(cells, start=2):
            formulas = [f'=GOOGLETRANSLATE(B{row},"la","en")']
            for column, (_, language) in enumerate(WORSE, start=3):  # C is english, D the first worse level...
                above = f"{chr(ord('A') + column - 1)}{row}"
                formulas.append(f'=GOOGLETRANSLATE(GOOGLETRANSLATE({above},"en","{language}"),"{language}","en")')
            writer.writerow([cell.id, cell.latin, *formulas])


def _usable(text: str | None) -> str | None:
    text = (text or "").strip()
    return text if text and not text.startswith(("#", "Loading")) else None


def merge(cells: list[Cell], sheet_rows: list[dict]) -> list[dict]:
    """The cells that came back translated, each with its dig: the best guess, then each worse level. Errors, blanks
    and "translations" identical to the Latin are dropped; a dig stops at the first level that failed."""
    by_id = {int(row["id"]): row for row in sheet_rows if (row.get("id") or "").strip().isdigit()}
    entries = []
    for cell in cells:
        row = by_id.get(cell.id, {})
        english = _usable(row.get("english"))
        if not english or english.casefold() == cell.latin.casefold():
            continue
        levels = [english]
        for name, _ in WORSE:
            text = _usable(row.get(name))
            if text is None:
                break
            if text != levels[-1]:  # The same again isn't a level worth digging for.
                levels.append(text)
        entries.append({"id": cell.id, "page": cell.page, "box": list(cell.box), "latin": cell.latin,
                        "levels": levels})
    return entries


def find_download(folder: Path = Path.home() / "Downloads") -> Path | None:
    """The newest CSV in Downloads that's the translated sheet (its header has id, latin and english)."""
    for path in sorted(folder.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True):
        with path.open(encoding="utf-8-sig", errors="replace") as file:
            header = [column.strip().lower() for column in file.readline().split(",")]
        if {"id", "latin", "english"} <= set(header):
            return path
    return None


def main(argv: list[str]) -> None:
    if argv[:1] == ["extract"]:
        WORK.mkdir(exist_ok=True)
        print(f"Downloading the OCR from {ABBYY_URL} ...")
        with urllib.request.urlopen(ABBYY_URL, timeout=120) as response:
            cells = extract_cells(gzip.decompress(response.read()))
        (WORK / "herbal_cells.json").write_text(json.dumps([asdict(c) for c in cells], indent=1), encoding="utf-8")
        write_sheet(cells, WORK / "herbal_cells.csv")
        print(f"{len(cells)} cells. Now import {WORK / 'herbal_cells.csv'} into Google Sheets (see the top of this file).")
    elif argv[:1] == ["merge"] and len(argv) <= 2:
        download = Path(argv[1]) if len(argv) == 2 else find_download()
        if download is None:
            sys.exit(f"No translated sheet in {Path.home() / 'Downloads'}. Download it from Google Sheets as CSV first.")
        print(f"Reading {download}")
        cells = [Cell(c["id"], c["page"], tuple(c["box"]), c["latin"])
                 for c in json.loads((WORK / "herbal_cells.json").read_text(encoding="utf-8"))]
        with open(download, newline="", encoding="utf-8-sig") as file:
            entries = merge(cells, list(csv.DictReader(file)))
        OUTPUT.write_text(json.dumps(entries, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{len(entries)} translations written to {OUTPUT}. Restart the bot and try /herbal.")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
