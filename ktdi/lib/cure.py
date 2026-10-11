"""Finding the ailment someone means, however they put it: "tickly throat", "my throat is tickly", "diarhea".

No AI: the names in ktdi/lib/ailments.py, matched loosely by ktdi/lib/fuzzy.py (any word order, small typos). Returns
None for things nobody could match ("dave"); /cure then falls back on All-heal. /plant finds herbs the same way, by
Culpeper's names for them or their Latin name.
"""

from dataclasses import dataclass
from functools import cache

from ktdi.lib import fuzzy
from ktdi.lib.ailments import AILMENTS, Ailment


@dataclass
class Match:
    ailment: Ailment
    name: str  # The name it matched ("tickly throat"), which may not be the ailment's main one.
    exact: bool


@cache
def index() -> fuzzy.Index:
    return fuzzy.index((ailment, name) for ailment in AILMENTS for name in ailment.names)


def find(query: str) -> Match | None:
    found = fuzzy.best_match(query, index())
    return Match(found.thing, found.name, found.exact) if found else None


def suggestions(typed: str, limit: int = 25) -> list[str]:
    if not typed.strip():
        return [ailment.name for ailment in AILMENTS][:limit]
    return fuzzy.starting_first(typed, [name for _, name, _ in index()], limit)


# Plants, for /plant: by any of Culpeper's names for them, or the Latin one.

@dataclass
class HerbMatch:
    herb: dict  # An entry from cures.json's "herbs"
    name: str  # The name it matched ("Ground-Ivy", "Glechoma hederacea")
    exact: bool


def herb_names(herb: dict) -> list[str]:
    latin = [name.strip() for name in (herb["latin"] or "").split(",") if name.strip()]
    return list(dict.fromkeys([*herb["aliases"], *latin, herb["name"]]))


def herb_index(herbs: list[dict]) -> fuzzy.Index:
    return fuzzy.index((herb, name) for herb in herbs for name in herb_names(herb))


def find_herb(query: str, entries: fuzzy.Index) -> HerbMatch | None:
    # Plant names are short and alike ("dave" is nearly "avens", "salvia" nearly "salix"), so spelling counts for less.
    found = fuzzy.best_match(query, entries, spelling=fuzzy.STRICT_SPELLING)
    return HerbMatch(found.thing, found.name, found.exact) if found else None
