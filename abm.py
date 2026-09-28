"""Anything But Metric: turn metric measurements into absurd (but defensible) reference units."""

import json
import math
import random
import re
from pathlib import Path

DATA_FILE = Path(__file__).parent / "abm_units.json"

# Results in this range read well ("3.2 bananas", "40% of a golf ball"); results in the sweet spot are favoured.
PREFERRED_RANGE = (0.25, 250)
SWEET_SPOT = (1, 50)
# Chance of ignoring the sensible range entirely, for gloriously ridiculous answers.
RIDICULOUS_CHANCE = 0.1

DIMENSION_EMOJI = {
    "length": "📏", "area": "🗺️", "volume": "🪣", "mass": "⚖️", "time": "⏱️", "speed": "🏎️",
    "acceleration": "🚀", "pressure": "🎈", "power": "🔌", "energy": "⚡", "temperature": "🌡️",
    "sound_level": "🔊",
}

# Units people can type, as unit -> (dimension, factor to that dimension's SI unit).
# Temperature is handled separately because it has an offset.
INPUT_UNITS: dict[str, tuple[str, float]] = {}
# The main symbol for each input unit, by dimension, for the help text.
INPUT_SYMBOLS: dict[str, list[str]] = {}


def _add(dimension: str, factor: float, *names: str) -> None:
    for name in names:
        INPUT_UNITS[name] = (dimension, factor)
    INPUT_SYMBOLS.setdefault(dimension, []).append(names[0])


_add("length", 1e-9, "nm", "nanometre", "nanometres", "nanometer", "nanometers")
_add("length", 1e-6, "µm", "um", "micron", "microns", "micrometre", "micrometres", "micrometer", "micrometers")
_add("length", 1e-3, "mm", "millimetre", "millimetres", "millimeter", "millimeters")
_add("length", 1e-2, "cm", "centimetre", "centimetres", "centimeter", "centimeters")
_add("length", 1e-1, "dm", "decimetre", "decimetres", "decimeter", "decimeters")
_add("length", 1, "m", "metre", "metres", "meter", "meters")
_add("length", 1e3, "km", "kilometre", "kilometres", "kilometer", "kilometers")
_add("area", 1e-6, "mm2", "mm²")
_add("area", 1e-4, "cm2", "cm²")
_add("area", 1, "m2", "m²", "sqm")
_add("area", 1e4, "ha", "hectare", "hectares")
_add("area", 1e6, "km2", "km²")
_add("volume", 1e-6, "ml", "mL", "millilitre", "millilitres", "milliliter", "milliliters", "cm3", "cm³", "cc")
_add("volume", 1e-5, "cl", "cL", "centilitre", "centilitres", "centiliter", "centiliters")
_add("volume", 1e-4, "dl", "dL")
_add("volume", 1e-3, "l", "L", "litre", "litres", "liter", "liters")
_add("volume", 1, "m3", "m³")
_add("volume", 1e9, "km3", "km³")
_add("mass", 1e-6, "mg", "milligram", "milligrams")
_add("mass", 1e-3, "g", "gram", "grams")
_add("mass", 1, "kg", "kilogram", "kilograms", "kilo", "kilos")
_add("mass", 1e3, "t", "tonne", "tonnes")
_add("time", 1e-3, "ms", "millisecond", "milliseconds")
_add("time", 1, "s", "sec", "secs", "second", "seconds")
_add("time", 60, "min", "mins", "minute", "minutes")
_add("time", 3600, "h", "hr", "hrs", "hour", "hours")
_add("time", 86400, "day", "days")
_add("time", 604800, "week", "weeks")
_add("time", 31536000, "yr", "yrs", "year", "years")
_add("speed", 1, "m/s", "mps")
_add("speed", 1 / 3.6, "km/h", "kmh", "kph", "kmph")
_add("acceleration", 1, "m/s2", "m/s²")
_add("pressure", 1, "Pa", "pascal", "pascals")
_add("pressure", 100, "hPa", "mbar")
_add("pressure", 1e3, "kPa")
_add("pressure", 1e6, "MPa")
_add("pressure", 1e5, "bar")
_add("power", 1e-3, "mW")
_add("power", 1, "W", "watt", "watts")
_add("power", 1e3, "kW", "kilowatt", "kilowatts")
_add("power", 1e6, "MW", "megawatt", "megawatts")
_add("power", 1e9, "GW", "gigawatt", "gigawatts")
_add("energy", 1, "J", "joule", "joules")
_add("energy", 1e3, "kJ")
_add("energy", 1e6, "MJ")
_add("energy", 1e9, "GJ")
_add("energy", 3600, "Wh")
_add("energy", 3.6e6, "kWh")
_add("energy", 4.184, "cal")
_add("energy", 4184, "kcal")
_add("sound_level", 1, "dB", "decibel", "decibels")

TEMPERATURE_INPUTS = {
    **dict.fromkeys(["c", "°c", "celsius", "degc"], lambda x: x + 273.15),
    **dict.fromkeys(["k", "kelvin"], lambda x: x),
    **dict.fromkeys(["f", "°f", "fahrenheit", "degf"], lambda x: (x - 32) * 5 / 9 + 273.15),
}


def _lowercase_lookup() -> dict[str, tuple[str, float]]:
    """Case-insensitive fallback, leaving out clashes like mW/MW."""
    lookup: dict[str, tuple[str, float]] = {}
    clashes = set()
    for name, value in INPUT_UNITS.items():
        key = name.lower()
        if key in lookup and lookup[key] != value:
            clashes.add(key)
        lookup[key] = value
    return {key: value for key, value in lookup.items() if key not in clashes}


INPUT_UNITS_LOWER = _lowercase_lookup()

MEASUREMENT_RE = re.compile(r"^\s*([-+]?(?:\d[\d,]*(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?)\s*(.+?)\s*$", re.IGNORECASE)

USAGE = "Give me a number and a metric unit, like `3cm`, `20C`, `2.5 kg`, `100 km/h`, `500ml` or `85dB`."


def input_unit_help() -> list[tuple[str, str]]:
    """(dimension, units) pairs listing what can be typed, for /help abm."""
    symbols = {**INPUT_SYMBOLS, "temperature": ["°C", "K", "°F"]}
    order = ["length", "area", "volume", "mass", "temperature", "time", "speed", "acceleration",
             "pressure", "power", "energy", "sound_level"]
    return [
        (f"{DIMENSION_EMOJI[dimension]} {dimension.replace('_', ' ').capitalize()}",
         " ".join(f"`{symbol}`" for symbol in symbols[dimension]))
        for dimension in order
    ]


class ABMError(ValueError):
    """A problem with what the user typed. The message is safe to show them."""


def load_units(path: Path = DATA_FILE) -> dict[str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    by_dimension: dict[str, list[dict]] = {name: [] for name in data["dimensions"]}
    for unit in data["units"]:
        by_dimension[unit["dimension"]].append(unit)
    return by_dimension


UNITS = load_units()


def parse(text: str) -> tuple[float, str, float]:
    """Parse "3cm" into (3.0, "length", 0.03). Temperatures come back in kelvin."""
    match = MEASUREMENT_RE.match(text)
    if not match:
        raise ABMError(f"I couldn't read `{text}`. {USAGE}")
    number = float(match.group(1).replace(",", ""))
    unit = match.group(2)
    if unit.lower() in TEMPERATURE_INPUTS:
        return number, "temperature", TEMPERATURE_INPUTS[unit.lower()](number)
    found = INPUT_UNITS.get(unit) or INPUT_UNITS_LOWER.get(unit.lower())
    if found is None:
        raise ABMError(f"I don't know the unit `{unit}`. {USAGE}")
    dimension, factor = found
    return number, dimension, number * factor


def with_article(unit: dict) -> str:
    article = unit.get("article")
    name = unit["name"]
    if article is None:
        if name.startswith(("US ", "UK ")):
            article = "a"
        elif name[0] == "8" or name[0].lower() in "aeiou":
            article = "an"
        else:
            article = "a"
    return f"{article} {name}" if article else name


def _sig(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}g}"


def _scientific(value: float) -> str:
    mantissa, exponent = f"{value:.2e}".split("e")
    superscript = str(int(exponent)).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))
    return f"{float(mantissa):g} × 10{superscript}"


def format_number(value: float) -> str:
    if value >= 1e15:
        return _scientific(value)
    for size, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if value >= size:
            return f"{_sig(value / size)} {word}"
    if value >= 1000:
        return f"{round(float(_sig(value))):,}"
    return _sig(value)


def _ordinal(number: int) -> str:
    if 10 <= number % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")


def format_fraction(value: float) -> str | None:
    """Turn a value below 1 into '1/6th', '40%' or '1/10 millionth'. None if it's too small for a nice fraction."""
    if value >= PREFERRED_RANGE[0]:
        return f"{round(value * 100)}%"
    denominator = 1 / value
    if denominator >= 1e15:
        return None
    if denominator >= 1e6:
        return f"1/{format_number(denominator)}th"
    whole = round(float(_sig(denominator)))
    return f"1/{whole:,}{_ordinal(whole)}"


def _weight(unit: dict, value: float) -> float:
    weight = 3 if SWEET_SPOT[0] <= value <= SWEET_SPOT[1] else 1
    # Everyday units like inches and pints are less surprising than bananas and giraffes, so pick them less often.
    if "us_customary" in unit.get("tags", []):
        weight /= 2
    return weight


def pick_unit(si_value: float, dimension: str) -> tuple[dict, float]:
    """Choose an absurd unit that gives a readable number, with the odd deliberately ridiculous one."""
    options = [(unit, si_value / unit["si_value"]) for unit in UNITS[dimension]]
    if random.random() < RIDICULOUS_CHANCE:
        return random.choice(options)
    low, high = PREFERRED_RANGE
    in_range = [(unit, value) for unit, value in options if low <= value <= high]
    if in_range:
        weights = [_weight(unit, value) for unit, value in in_range]
        return random.choices(in_range, weights=weights)[0]
    # Nothing reads nicely, so pick one of the closest to the sweet spot.
    target = math.log10(10)
    closest = sorted(options, key=lambda option: abs(math.log10(option[1]) - target))[:3]
    return random.choice(closest)


def describe(value: float, unit: dict) -> str:
    """'3.2 bananas', '40% of a golf ball', '1/6th of a banana'."""
    if value >= 1:
        count = format_number(value)
        return f"{count} {unit['name'] if count == '1' else unit['plural']}"
    fraction = format_fraction(value)
    if fraction is None:
        return f"{_scientific(value)} of {with_article(unit)}"
    return f"{fraction} of {with_article(unit)}"


def describe_temperature(kelvin: float, unit: dict) -> str:
    ratio = kelvin / unit["si_value"]
    reference = with_article(unit)
    if 0.95 <= ratio <= 1.05:
        comparison = f"about as hot as {reference}"
    elif ratio >= 1:
        comparison = f"{format_number(ratio)} times as hot as {reference}"
    else:
        fraction = format_fraction(ratio) or _scientific(ratio)
        comparison = f"{fraction} as hot as {reference}"
    return f"{comparison} (comparing in kelvin)."


def describe_sound(decibels: float) -> str:
    # dB is logarithmic, so compare against the nearest reference point instead of dividing.
    unit = min(UNITS["sound_level"], key=lambda u: abs(u["si_value"] - decibels))
    difference = decibels - unit["si_value"]
    reference = with_article(unit)
    if abs(difference) < 2.5:
        return f"about as loud as {reference}"
    louder_or_quieter = "louder" if difference > 0 else "quieter"
    return f"{format_number(abs(difference))} dB {louder_or_quieter} than {reference}"


def convert(text: str) -> str:
    """The full reply for `abm <text>`."""
    number, dimension, si_value = parse(text)
    emoji = DIMENSION_EMOJI.get(dimension, "📐")
    shown = text.strip()

    if dimension == "sound_level":
        return f"{emoji} {shown} is {describe_sound(si_value)}."
    if dimension == "temperature":
        if si_value <= 0:
            return f"{emoji} {shown} is at or below absolute zero. Physics would like a word."
        unit, _ = pick_unit(si_value, dimension)
        return f"{emoji} {shown} is {describe_temperature(si_value, unit)}"
    if si_value <= 0:
        return f"{emoji} {shown} is… nothing. That's 0 of everything. Try a positive number."

    unit, value = pick_unit(si_value, dimension)
    about = "about " if unit["accuracy"] == "approximate" else ""
    return f"{emoji} {shown} is {about}{describe(value, unit)}."


# --- Sincere imperial / US customary conversions (for /imperial) ---
# Exact definitions, in SI units.
INCH = 0.0254
FOOT = 0.3048
MILE = 1609.344
OUNCE = 0.028349523125
POUND = 0.45359237
STONE = 6.35029318
US_TON = 907.18474
UK_TON = 1016.0469088
US_TSP = 4.92892159375e-06
US_TBSP = 1.478676478125e-05
US_FL_OZ = 2.95735295625e-05
UK_FL_OZ = 2.84130625e-05
US_PINT = 0.000473176473
UK_PINT = 0.00056826125
US_GALLON = 0.003785411784
UK_GALLON = 0.00454609
CUBIC_FOOT = 0.028316846592
ACRE_FOOT = 1233.48183754752
SQ_INCH = 0.00064516
SQ_FOOT = 0.09290304
ACRE = 4046.8564224
SQ_MILE = 2589988.110336
MPH = 0.44704
PSI = 6894.757293168
IN_HG = 3386.389
HORSEPOWER = 745.6998715822702
BTU_PER_HOUR = 0.2930710701722222
BTU = 1055.05585262
THERM = 105505585.262
FOOD_CALORIE = 4184
STANDARD_GRAVITY = 9.80665


def plain_number(value: float) -> str:
    """Sensible precision for a sincere answer: 2,625 / 165.4 / 5.51 / 0.0394."""
    if value == 0:
        return "0"
    if value >= 1e9 or value < 0.001:
        return _scientific(value)
    if value >= 1000:
        return f"{value:,.0f}"
    decimals = 1 if value >= 100 else 2 if value >= 1 else None
    if decimals is None:
        return _sig(value)
    return f"{value:.{decimals}f}".rstrip("0").rstrip(".")


def _compound(si_value: float, big: float, small: float, big_label: str, small_label: str) -> str:
    """Split into two units, e.g. 5 ft 10.9 in or 11 st 11.3 lb."""
    total_small = si_value / small
    per_big = round(big / small)
    whole = int(total_small // per_big)
    rest = round(total_small - whole * per_big, 1)
    if rest >= per_big:  # Rounding pushed it over, e.g. 5 ft 12.0 in.
        whole, rest = whole + 1, 0
    if rest == 0:
        return f"{whole} {big_label}"
    return f"{whole} {big_label} {plain_number(rest)} {small_label}"


def _with_decimal(compound: str, value: float, label: str) -> str:
    """'5 ft 10.9 in (5.91 ft)', but just '6 ft' when it's a whole number."""
    decimal = f"{plain_number(value)} {label}"
    return compound if compound == decimal else f"{compound} ({decimal})"


def imperial_length(metres: float) -> str:
    if metres < FOOT:
        return f"{plain_number(metres / INCH)} in"
    if metres < 3:
        return _with_decimal(_compound(metres, FOOT, INCH, "ft", "in"), metres / FOOT, "ft")
    if metres < MILE / 2:
        return f"{plain_number(metres / FOOT)} ft"
    return f"{plain_number(metres / MILE)} mi"


def imperial_mass(kg: float) -> str:
    if kg < POUND:
        return f"{plain_number(kg / OUNCE)} oz"
    if kg < 20 * POUND:
        return _with_decimal(_compound(kg, POUND, OUNCE, "lb", "oz"), kg / POUND, "lb")
    pounds = f"{plain_number(kg / POUND)} lb"
    if kg < 250:
        return f"{pounds} ({_compound(kg, STONE, POUND, 'st', 'lb')})"
    if kg < US_TON:
        return pounds
    return f"{pounds} ({plain_number(kg / US_TON)} US tons, {plain_number(kg / UK_TON)} UK tons)"


def imperial_volume(m3: float) -> str:
    if m3 < US_TBSP:
        return f"{plain_number(m3 / US_TSP)} US tsp"
    if m3 < US_FL_OZ:
        return f"{plain_number(m3 / US_TBSP)} US tbsp"
    if m3 < 0.5e-3:
        return f"{plain_number(m3 / US_FL_OZ)} US fl oz ({plain_number(m3 / UK_FL_OZ)} UK fl oz)"
    if m3 < 4e-3:
        return f"{plain_number(m3 / US_PINT)} US pints ({plain_number(m3 / UK_PINT)} UK pints)"
    if m3 < 1:
        return f"{plain_number(m3 / US_GALLON)} US gal ({plain_number(m3 / UK_GALLON)} UK gal)"
    if m3 < ACRE_FOOT:
        return f"{plain_number(m3 / CUBIC_FOOT)} cu ft ({plain_number(m3 / US_GALLON)} US gal)"
    return f"{plain_number(m3 / ACRE_FOOT)} acre-feet"


def imperial_area(m2: float) -> str:
    if m2 < SQ_FOOT:
        return f"{plain_number(m2 / SQ_INCH)} sq in"
    if m2 < ACRE:
        return f"{plain_number(m2 / SQ_FOOT)} sq ft"
    if m2 < SQ_MILE:
        return f"{plain_number(m2 / ACRE)} acres"
    return f"{plain_number(m2 / SQ_MILE)} sq mi"


def imperial_time(seconds: float) -> str:
    parts = []
    remaining = seconds
    for size, label in ((86400, "d"), (3600, "h"), (60, "min")):
        if remaining >= size:
            count = int(remaining // size)
            parts.append(f"{count:,} {label}")
            remaining -= count * size
    if remaining or not parts:
        parts.append(f"{plain_number(remaining)} s")
    return " ".join(parts)


def imperial_energy(joules: float) -> str:
    btu = f"{plain_number(joules / BTU)} BTU"
    if joules >= THERM:
        return f"{btu} ({plain_number(joules / THERM)} therms)"
    return f"{btu} ({plain_number(joules / FOOD_CALORIE)} food Calories)"


def _degrees(value: float) -> str:
    text = f"{value:,.1f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


IMPERIAL_CONVERTERS = {
    "length": imperial_length,
    "mass": imperial_mass,
    "volume": imperial_volume,
    "area": imperial_area,
    "time": imperial_time,
    "speed": lambda v: f"{plain_number(v / MPH)} mph ({plain_number(v / FOOT)} ft/s)",
    "acceleration": lambda v: f"{plain_number(v / FOOT)} ft/s² ({plain_number(v / STANDARD_GRAVITY)} g)",
    "pressure": lambda v: f"{plain_number(v / PSI)} psi ({plain_number(v / IN_HG)} inHg)",
    "power": lambda v: f"{plain_number(v / HORSEPOWER)} hp ({plain_number(v / BTU_PER_HOUR)} BTU/h)",
    "energy": imperial_energy,
}


IMPERIAL_SIGN_OFF = "❤️"


def to_imperial(text: str) -> str:
    """The full reply for `imperial <text>`: a straight, accurate conversion, with love."""
    return f"{_imperial_reply(text)} {IMPERIAL_SIGN_OFF}"


def _imperial_reply(text: str) -> str:
    number, dimension, si_value = parse(text)
    emoji = DIMENSION_EMOJI.get(dimension, "📐")
    shown = text.strip()

    if dimension == "sound_level":
        return f"{emoji} {shown}. Decibels aren't metric, so it's the same in imperial."
    if dimension == "temperature":
        if si_value < 0:
            return f"{emoji} {shown} is below absolute zero, so it can't be converted."
        celsius = si_value - 273.15
        if re.search(r"(°?f|fahrenheit|degf)$", shown, re.IGNORECASE):
            return f"{emoji} {shown} is already Fahrenheit. In Celsius it's **{_degrees(celsius)} °C**."
        return f"{emoji} {shown} = **{_degrees(celsius * 9 / 5 + 32)} °F**"
    if si_value < 0:
        return f"{emoji} {shown} is negative, so there's nothing to convert."
    reply = f"{emoji} {shown} = **{IMPERIAL_CONVERTERS[dimension](si_value)}**"
    if dimension == "time":
        reply += " (time isn't metric, so it's the same everywhere)"
    return reply
