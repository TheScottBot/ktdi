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
    # Plain imperial units are less funny than bananas and giraffes.
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


def describe_temperature(kelvin: float, unit: dict, typed_fahrenheit: bool = False) -> str:
    ratio = kelvin / unit["si_value"]
    reference = with_article(unit)
    if 0.95 <= ratio <= 1.05:
        comparison = f"about as hot as {reference}"
    elif ratio >= 1:
        comparison = f"{format_number(ratio)} times as hot as {reference}"
    else:
        fraction = format_fraction(ratio) or _scientific(ratio)
        comparison = f"{fraction} as hot as {reference}"
    if typed_fahrenheit:
        return f"{comparison} (in kelvin, obviously). Also, you typed Fahrenheit into a metric converter. Bold."
    fahrenheit = round((kelvin - 273.15) * 9 / 5 + 32)
    return f"{comparison} (in kelvin, obviously). That's {fahrenheit:,}°F for the freedom-inclined."


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
        typed_fahrenheit = re.search(r"(°?f|fahrenheit|degf)$", shown, re.IGNORECASE) is not None
        return f"{emoji} {shown} is {describe_temperature(si_value, unit, typed_fahrenheit)}"
    if si_value <= 0:
        return f"{emoji} {shown} is… nothing. That's 0 of everything. Try a positive number."

    unit, value = pick_unit(si_value, dimension)
    about = "about " if unit["accuracy"] == "approximate" else ""
    return f"{emoji} {shown} is {about}{describe(value, unit)}."
