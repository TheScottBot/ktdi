"""Today's weather from Open-Meteo (https://open-meteo.com): free, no key, any place in the world.

geocode() turns a place name into coordinates; forecast() gets today's weather there. Both return None when the place
isn't found or Open-Meteo can't be reached, so callers can carry on without it.
"""

from dataclasses import dataclass, field

import aiohttp

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = aiohttp.ClientTimeout(total=10)

# WMO weather codes: (description, emoji, what kind of weather it is).
CODES = {
    0: ("clear sky", "☀️", {"clear"}),
    1: ("mainly clear", "🌤️", {"clear"}),
    2: ("partly cloudy", "⛅", {"cloud"}),
    3: ("overcast", "☁️", {"cloud"}),
    45: ("fog", "🌫️", {"fog"}),
    48: ("freezing fog", "🌫️", {"fog", "frost"}),
    51: ("light drizzle", "🌦️", {"rain"}),
    53: ("drizzle", "🌦️", {"rain"}),
    55: ("heavy drizzle", "🌧️", {"rain"}),
    56: ("freezing drizzle", "🌧️", {"rain", "frost"}),
    57: ("heavy freezing drizzle", "🌧️", {"rain", "frost"}),
    61: ("light rain", "🌦️", {"rain"}),
    63: ("rain", "🌧️", {"rain"}),
    65: ("heavy rain", "🌧️", {"rain"}),
    66: ("freezing rain", "🌧️", {"rain", "frost"}),
    67: ("heavy freezing rain", "🌧️", {"rain", "frost"}),
    71: ("light snow", "🌨️", {"snow"}),
    73: ("snow", "🌨️", {"snow"}),
    75: ("heavy snow", "❄️", {"snow"}),
    77: ("snow grains", "🌨️", {"snow"}),
    80: ("light showers", "🌦️", {"rain"}),
    81: ("showers", "🌧️", {"rain"}),
    82: ("violent showers", "⛈️", {"rain", "storm"}),
    85: ("snow showers", "🌨️", {"snow"}),
    86: ("heavy snow showers", "❄️", {"snow"}),
    95: ("thunderstorms", "⛈️", {"thunder", "storm", "rain"}),
    96: ("thunderstorms with hail", "⛈️", {"thunder", "storm", "hail"}),
    99: ("thunderstorms with heavy hail", "⛈️", {"thunder", "storm", "hail"}),
}
UNKNOWN = ("weather", "🌡️", set())
WINDY_MPH = 25  # A day with gusts of wind this strong counts as windy.
HOT_C, COLD_C = 25, 5  # Highs at or above HOT_C are hot; at or below COLD_C, cold.


@dataclass
class Place:
    name: str  # "Manchester, England, United Kingdom"
    latitude: float
    longitude: float


@dataclass
class Forecast:
    place: Place
    now_c: float
    now_code: int
    high_c: float
    low_c: float
    code: int  # Today's overall weather
    rain_chance: int | None  # % chance of rain at some point today
    wind_mph: float  # Today's strongest wind
    kinds: set[str] = field(default_factory=set)  # What sort of day it is: rain, frost, wind...


def describe(code: int) -> tuple[str, str]:
    description, emoji, _ = CODES.get(code, UNKNOWN)
    return description, emoji


def kinds_of_weather(code: int, now_code: int, high_c: float, low_c: float, rain_chance: int | None,
                     wind_mph: float) -> set[str]:
    """The weather tags the lore uses (rain, snow, frost, hail, thunder, fog, wind, clear, cloud, hot, cold, dry,
    storm) for today."""
    kinds = set(CODES.get(code, UNKNOWN)[2]) | set(CODES.get(now_code, UNKNOWN)[2])
    if low_c <= 0:
        kinds.add("frost")
    if high_c >= HOT_C:
        kinds.add("hot")
    if high_c <= COLD_C:
        kinds.add("cold")
    if wind_mph >= WINDY_MPH:
        kinds.add("wind")
    if (rain_chance or 0) <= 10 and not kinds & {"rain", "snow", "hail"}:
        kinds.add("dry")
    return kinds


def parse_place(response: dict, qualifiers: list[str] = ()) -> Place | None:
    """The best match (Open-Meteo lists the likeliest first). Qualifiers ("Cumbria" in "Highbridge, Cumbria") pick
    the first that's in all of them, by county, region, country or country code."""
    results = (response or {}).get("results") or []
    wanted = [q.casefold() for q in qualifiers]
    for found in results:
        areas = [str(found.get(key) or "").casefold() for key in ("admin1", "admin2", "admin3", "country", "country_code")]
        if all(any(q in area for area in areas) for q in wanted):
            parts = (found.get("name"), found.get("admin2"), found.get("admin1"), found.get("country"))
            return Place(", ".join(dict.fromkeys(p for p in parts if p)), found["latitude"], found["longitude"])
    return None


def parse_forecast(place: Place, response: dict) -> Forecast | None:
    try:
        now, daily = response["current"], response["daily"]
        rain = (daily.get("precipitation_probability_max") or [None])[0]
        values = dict(now_c=now["temperature_2m"], now_code=now["weather_code"], high_c=daily["temperature_2m_max"][0],
                      low_c=daily["temperature_2m_min"][0], code=daily["weather_code"][0],
                      rain_chance=None if rain is None else int(rain), wind_mph=daily["wind_speed_10m_max"][0])
    except (KeyError, IndexError, TypeError):
        return None
    if any(values[key] is None for key in ("now_c", "now_code", "high_c", "low_c", "code", "wind_mph")):
        return None
    return Forecast(place, **values, kinds=kinds_of_weather(**{k: v for k, v in values.items() if k != "now_c"}))


_places: dict[str, Place | None] = {}  # Place names already looked up (they don't move).


async def _get(session: aiohttp.ClientSession, url: str, params: dict) -> dict | None:
    async with session.get(url, params=params) as response:
        return await response.json() if response.status == 200 else None


async def geocode(name: str, remember: bool = True) -> Place | None:
    """A place by name: "Highbridge", or "Highbridge, Cumbria" to pick one of several. remember=False for where
    someone is (/weather here): it's neither taken from nor kept in the cache."""
    key = " ".join(name.split()).casefold()
    if not remember or key not in _places:
        town, *qualifiers = [part.strip() for part in name.split(",") if part.strip()] or [""]
        try:
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                response = await _get(session, GEOCODE_URL, {"name": town, "count": 10, "language": "en"})
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return None  # Not cached: try again next time.
        if response is None:
            return None
        found = parse_place(response, qualifiers)
        if not remember:
            return found
        _places[key] = found
    return _places[key]


async def forecast(place: Place) -> Forecast | None:
    params = {"latitude": place.latitude, "longitude": place.longitude, "timezone": "auto", "forecast_days": 1,
              "wind_speed_unit": "mph", "current": "temperature_2m,weather_code",
              "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                       "wind_speed_10m_max"}
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            response = await _get(session, FORECAST_URL, params)
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return None
    return parse_forecast(place, response) if response else None
