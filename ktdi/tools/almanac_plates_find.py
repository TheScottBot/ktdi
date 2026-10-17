"""Find candidate pictures of /almanac's plants of the day on Wikimedia Commons, for someone to look at: dev only.
python -m ktdi.tools.almanac_plates_find [--plant "Draba verna"] [--search "Aesculus hippocastanum"] [--check]

Hone gives each day a plant ("Early Witlow grass. _Draba verna._"), and /almanac shows a botanical plate of it: an
old engraving, woodcut or painting, coloured, public domain. Which plate goes with which plant is decided by a person
(or an agent told to look at every picture) and recorded in ktdi/lib/almanac_plates.json; this only finds candidates.

For each plant (or just --plant), it asks Commons for the files in "Category:<Name> - botanical illustrations", then
searches the file pages for the name, keeps the public-domain ones (Commons' licence metadata: "Public domain", "No
restrictions", CC0) and writes them, with each file's description, date, artist and categories, to
private/almanac/candidates/<plant>.json, with a small copy of each (330 px) in private/almanac/thumbs/<plant>/ to
look at. --search looks under another name (Hone's Latin is often misspelt or out of date: "Larnium garganicum" is
Lamium garganicum) but files the results under the plant's.

--bhl looks in the Biodiversity Heritage Library instead, for the plants Commons hasn't got: BHL indexes where a
name appears in its scanned books, and the plate is usually a page or two either side, marked as an illustration. It
keeps those, from volumes BHL says are public domain, as private/almanac/candidates/<plant>.bhl.json. It needs a
free BHL API key, as BHL_API_KEY in .env.dev (never .env: the bot doesn't use it).

--check asks for every picture in ktdi/lib/almanac_plates.json and lists any that have gone (Commons files get
renamed or deleted now and then; the bot links to them rather than keeping copies).
"""

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ktdi.tools import gutenberg

API = "https://commons.wikimedia.org/w/api.php"
BHL_API = "https://www.biodiversitylibrary.org/api3"
NEAR = 3  # How many pages either side of a name's mention a BHL plate may be
USER_AGENT = "KTDI-almanac-plates/1.0 (a Discord bot's dev tool; looks up public-domain botanical plates)"
ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "private" / "almanac"
PLATES = gutenberg.LIB / "almanac_plates.json"
FREE = re.compile(r"public domain|no restrictions|cc0|^pd", re.I)
WIDTH, THUMB = 960, 330  # Commons only serves standard widths (500, 960, 1280...); others give 400s
SMALLEST = 500  # Pixels, the shorter side: smaller pictures look poor in Discord
LATIN = re.compile(r"_([^_]+)_")


def plants() -> dict[str, list[str]]:
    """Every plant of the day, by Hone's Latin name ("Draba verna"), with the days it's on."""
    days = json.loads((gutenberg.LIB / "almanac.json").read_text(encoding="utf-8"))["days"]
    found: dict[str, list[str]] = {}
    for date, day in days.items():
        names = LATIN.findall(day["flower"]["plant"]) if day["flower"] else []
        if names:
            found.setdefault(names[-1].strip(" ."), []).append(date)
    return found


def get(url: str, params: dict | None = None, pause: float = 1.0) -> bytes:
    """A page or file, politely: a User-Agent, a pause after each, and when Commons says it's busy (429), waiting as
    long as it asks before trying again."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                time.sleep(pause)
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503) or attempt == 5:
                raise
            wait = error.headers.get("Retry-After", "")
            time.sleep(int(wait) if wait.isdigit() else 30 * (attempt + 1))
    raise RuntimeError("unreachable")


def api(**params) -> dict:
    return json.loads(get(API, {"action": "query", "format": "json", "formatversion": 2, **params}))


def titles_for(name: str, limit: int = 10) -> list[str]:
    """Commons file titles that may show the plant: its botanical-illustrations category first, then a search."""
    genus, _, rest = name.partition(" ")
    proper = f"{genus[:1].upper()}{genus[1:].lower()} {rest.lower()}".strip()
    found: list[str] = []
    for category in (f"Category:{proper} - botanical illustrations", f"Category:{proper}"):
        members = api(list="categorymembers", cmtitle=category, cmtype="file", cmlimit=limit)
        found += [m["title"] for m in members.get("query", {}).get("categorymembers", [])]
        if len(found) >= limit:
            break
    for query in (f'"{proper}" illustration', f'"{proper}" plate', f'"{proper}"'):
        if len(found) >= limit:
            break
        hits = api(list="search", srsearch=query, srnamespace=6, srlimit=limit)
        found += [h["title"] for h in hits.get("query", {}).get("search", [])]
    return list(dict.fromkeys(found))[:limit]


def plain(text) -> str:
    """Commons' metadata as plain text (it's HTML, and now and then a number)."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(text or ""))).split())


def details(titles: list[str]) -> list[dict]:
    """Each file's picture (at WIDTH), page, licence, artist, date, description and categories; public domain only."""
    if not titles:
        return []
    info = api(titles="|".join(titles), prop="imageinfo|categories", iiprop="url|extmetadata|mime|size",
               iiurlwidth=WIDTH, cllimit="max", clshow="!hidden")
    found = []
    for page in info.get("query", {}).get("pages", []):
        image = (page.get("imageinfo") or [{}])[0]
        meta = {key: plain(value.get("value", "")) for key, value in image.get("extmetadata", {}).items()}
        licence = meta.get("LicenseShortName", "")
        if not image.get("thumburl") or not FREE.search(licence) or not image.get("mime", "").startswith("image/"):
            continue
        if min(image.get("width") or 0, image.get("height") or 0) < SMALLEST:
            continue  # Too small to look good in Discord
        try:
            picture = clean(image["thumburl"]) if "/thumb/" in image["thumburl"] else thumbnail(page["title"])
        except ValueError:
            continue  # No standard size Commons will serve it at
        found.append({"file": page["title"], "page": image.get("descriptionurl"), "image": picture,
                      "size": [image.get("width"), image.get("height")], "licence": licence,
                      "artist": meta.get("Artist", "")[:200], "date": meta.get("DateTimeOriginal", "")[:80],
                      "description": meta.get("ImageDescription", "")[:600],
                      "categories": [c["title"].removeprefix("Category:") for c in page.get("categories", [])][:15]})
    return found


def clean(url: str) -> str:
    """A Commons image URL without the tracking Commons adds to it ("?utm_source=...")."""
    return url.split("?", 1)[0]


def thumbnail(file: str) -> str:
    """A file's picture at a width Commons serves: 960 px, or for one smaller than that, 500. Never the file
    itself: Commons rate-limits those (429s), and asks for thumbnails at its standard sizes instead."""
    for width in (WIDTH, 500):
        info = api(titles=file, prop="imageinfo", iiprop="url", iiurlwidth=width)
        url = clean(((info["query"]["pages"][0].get("imageinfo") or [{}])[0]).get("thumburl", ""))
        if "/thumb/" in url:
            return url
    raise ValueError(f"{file} has no thumbnail Commons will serve")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def find(plant: str, search: str | None = None) -> list[dict]:
    """Candidates for a plant (looked up under `search`, if given), written to private/almanac with thumbnails."""
    found = details(titles_for(search or plant))
    folder = OUT / "thumbs" / slug(plant)
    folder.mkdir(parents=True, exist_ok=True)
    for n, candidate in enumerate(found, start=1):
        thumb = candidate["image"].replace(f"/{WIDTH}px-", f"/{THUMB}px-")
        try:
            (folder / f"{n}.jpg").write_bytes(get(thumb, pause=2.0))
            candidate["thumb"] = str(folder / f"{n}.jpg")
        except urllib.error.URLError as error:
            candidate["thumb"] = f"(couldn't fetch: {error})"
    (OUT / "candidates").mkdir(parents=True, exist_ok=True)
    (OUT / "candidates" / f"{slug(plant)}.json").write_text(
        json.dumps({"plant": plant, "searched": search or plant, "candidates": found}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return found


def bhl_key() -> str:
    """BHL_API_KEY from .env.dev (read here, not through ktdi.config: only this tool needs it)."""
    env = ROOT / ".env.dev"
    for line in env.read_text(encoding="utf-8").splitlines() if env.exists() else []:
        if line.startswith("BHL_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("--bhl needs BHL_API_KEY in .env.dev (a free key from biodiversitylibrary.org)")


def bhl(op: str, key: str, **params) -> list:
    reply = json.loads(get(BHL_API, {"op": op, "format": "json", "apikey": key, **params}, pause=1.0))
    if reply.get("Status") != "ok":
        raise RuntimeError(f"BHL {op}: {reply.get('ErrorMessage')}")
    return reply.get("Result") or []


def bhl_details(name: str, key: str, limit: int = 10) -> list[dict]:
    """Plates of the plant in BHL: illustration pages near where its name is mentioned, in public-domain volumes."""
    names = bhl("GetNameMetadata", key, name=name)
    mentions = [(item["ItemID"], page["PageID"], title.get("PublicationDate", ""))
                for found in names for title in found.get("Titles", []) for item in title.get("Items", [])
                for page in item.get("Pages", [])]
    found, seen, titles = [], set(), {}
    for item_id, page_id, year in mentions:
        if len(found) >= limit:
            break
        item = (bhl("GetItemMetadata", key, id=item_id, pages="t") or [None])[0]
        if not item or "public domain" not in (item.get("CopyrightStatus") or "").casefold():
            continue
        pages = item.get("Pages", [])
        at = next((n for n, page in enumerate(pages) if page["PageID"] == page_id), None)
        if at is None:
            continue
        if item["TitleID"] not in titles:
            title = (bhl("GetTitleMetadata", key, id=item["TitleID"]) or [{}])[0]
            titles[item["TitleID"]] = (title.get("FullTitle", "")[:200],
                                       ", ".join(a.get("Name", "") for a in title.get("Authors", []))[:120])
        for page in pages[max(0, at - NEAR):at + NEAR + 1]:
            kinds = " ".join(t["PageTypeName"].strip() for t in page.get("PageTypes", []))
            if "Illustration" in kinds and page["PageID"] not in seen:
                seen.add(page["PageID"])
                numbers = " ".join(f"{n.get('Prefix', '')} {n.get('Number', '')}".strip()
                                   for n in page.get("PageNumbers", []) if n)
                found.append({"file": f"BHL page {page['PageID']}", "page": page["PageUrl"],
                              "image": page["FullSizeImageUrl"], "thumb_url": page["ThumbnailUrl"],
                              "licence": item.get("CopyrightStatus", ""), "title": titles[item["TitleID"]][0],
                              "artist": titles[item["TitleID"]][1], "date": item.get("Year") or year,
                              "volume": item.get("Volume", ""), "plate": numbers,
                              "holder": item.get("HoldingInstitution", "")})
    return found


def find_bhl(plant: str, search: str | None = None) -> list[dict]:
    """BHL candidates for a plant, written next to the Commons ones, with thumbnails."""
    found = bhl_details(search or plant, bhl_key())
    folder = OUT / "thumbs" / slug(plant)
    folder.mkdir(parents=True, exist_ok=True)
    for n, candidate in enumerate(found, start=1):
        try:
            (folder / f"bhl-{n}.jpg").write_bytes(get(candidate["thumb_url"], pause=1.0))
            candidate["thumb"] = str(folder / f"bhl-{n}.jpg")
        except urllib.error.URLError as error:
            candidate["thumb"] = f"(couldn't fetch: {error})"
    (OUT / "candidates").mkdir(parents=True, exist_ok=True)
    (OUT / "candidates" / f"{slug(plant)}.bhl.json").write_text(
        json.dumps({"plant": plant, "searched": search or plant, "candidates": found}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return found


def check() -> list[str]:
    """The pictures in almanac_plates.json that no longer load."""
    plates = json.loads(PLATES.read_text(encoding="utf-8"))["plates"]
    gone = []
    for plant, plate in plates.items():
        if plate:
            try:
                get(plate["image"])
            except urllib.error.URLError as error:
                gone.append(f"{plant}: {plate['image']} ({error})")
    return gone


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--plant", help="One of Hone's plants, by his Latin name (default: all of them)")
    parser.add_argument("--search", help="Look it up under this name instead (with --plant)")
    parser.add_argument("--check", action="store_true", help="Check every picture in almanac_plates.json loads")
    parser.add_argument("--again", action="store_true", help="Look again for plants that already have candidates")
    parser.add_argument("--bhl", action="store_true", help="Look in the Biodiversity Heritage Library instead")
    args = parser.parse_args()
    if args.check:
        gone = check()
        print("\n".join(gone) or "Every picture loads.")
        sys.exit(1 if gone else 0)
    names = [args.plant] if args.plant else list(plants())
    for name in names:
        done = OUT / "candidates" / f"{slug(name)}{'.bhl' if args.bhl else ''}.json"
        if not args.plant and not args.again and done.exists():
            continue  # Done already (a run that stopped carries on where it was)
        found = find_bhl(name, args.search) if args.bhl else find(name, args.search)
        print(f"{name}: {len(found)} candidates")


if __name__ == "__main__":
    main()
