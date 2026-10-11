"""Old British money (pounds, shillings and pence, before 1971) in today's money, for Mrs Beeton's costs:
"2s. 3d. per quart" is "2s. 3d. per quart (about £17 now)".

12 pence (d) to the shilling (s), 20 shillings to the pound (£): 240d to the pound. Prices then are scaled by how
much prices have risen since: £1 in 1861 is about £155 now (ONS price indices, via inflation calculators such as
in2013dollars.com and officialdata.org, 2026). It's an estimate, so it's always "about".
"""

import re

PENCE_PER_POUND = 240
SINCE_1861 = 155  # £1 in 1861 is about £155 now
NUMBER = r"\d+(?:-\d+/\d+)?|\d+/\d+"  # "2", "1-1/2", "1/2"
# "£1 1s. 6d.", "2s. 3d", "1s, 6d", "1-1/2d.", and the odd "9 d" (but not "9 dozen")
AMOUNT = re.compile(rf"(?:£\s?(?P<pounds>{NUMBER})\.?\s*,?\s*)?(?:(?P<shillings>{NUMBER})\s?s\b\.?\s*,?\s*)?"
                    rf"(?:(?P<pence>{NUMBER})\s?d\b\.?)?")


def number(text: str | None) -> float:
    """"2" is 2, "1-1/2" is 1.5, "1/2" is 0.5."""
    if not text:
        return 0.0
    whole, _, fraction = text.partition("-")
    if "/" in whole:
        whole, fraction = "0", whole
    top, _, bottom = fraction.partition("/")
    return float(whole) + (float(top) / float(bottom) if bottom else 0.0)


def amounts(text: str) -> list[tuple[int, int, float]]:
    """The sums of money in a text, as (where it starts, where it ends, pence): "2s. 3d. per quart" has one, 27d."""
    found = []
    for match in AMOUNT.finditer(text):
        if not any(match.group(part) for part in ("pounds", "shillings", "pence")):
            continue
        pence = (number(match.group("pounds")) * PENCE_PER_POUND + number(match.group("shillings")) * 12
                 + number(match.group("pence")))
        found.append((match.start(), match.end(), pence))
    return found


def today(pence: float) -> str:
    """Old pence in today's money, rounded to what's worth saying: "£3.90", "£17", "£1,550"."""
    pounds = pence / PENCE_PER_POUND * SINCE_1861
    if pounds < 10:
        return f"£{round(pounds, 1):.2f}"
    if pounds < 100:
        return f"£{round(pounds):,}"
    return f"£{round(pounds, -1):,.0f}"


def in_todays_money(text: str) -> str:
    """A cost with today's money added: one sum ("2s. 3d. per quart (about £17 now)"), a range ("from 6d. to 8d.
    each (about £3.90–£5.20 now)"), or each of several sums after itself. A cost with no money in it is left alone."""
    found = amounts(text)
    if not found:
        return text
    if len(found) == 1:
        return f"{text.rstrip(' .')} (about {today(found[0][2])} now)"
    if len(found) == 2 and re.fullmatch(r"\s*to\s*", text[found[0][1]:found[1][0]]):  # "6d. to 8d."
        return f"{text.rstrip(' .')} (about {today(found[0][2])}–{today(found[1][2])} now)"
    for start, end, pence in reversed(found):  # Several separate sums: each its own
        rest = text[end:].lstrip()
        space = "" if not rest or rest[0] in ",.;" else " "
        text = f"{text[:end].rstrip()} (about {today(pence)}){space}{rest}"
    return text
