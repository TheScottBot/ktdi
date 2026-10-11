"""/weather: Open-Meteo's forecast next to Inwards' 1893 weather lore (ktdi.features.weather, ktdi.lib.openmeteo).
No real network calls."""

import types
from datetime import date

import pytest

from ktdi import config
from ktdi.features import weather
from ktdi.lib import openmeteo
from tests.fakes import Ctx, Interaction, User, run

SCOTT = User(1, "scott")
LONDON = openmeteo.Place("London, England, United Kingdom", 51.5, -0.13)
HIGHBRIDGE = openmeteo.Place("Highbridge, Somerset, England, United Kingdom", 51.22, -2.98)
SWITHIN = {"text": "St. Swithin's day if thou dost rain, / For forty days it will remain", "source": None,
           "months": [7], "date": "07-15", "weather": ["rain"]}
CAT = {"text": "When the cat washes her face over her ear, / The weather will be fine and clear", "source": None,
       "months": [], "date": None, "weather": ["clear"]}
FEBRUARY = {"text": "February fill dyke, / Be it black or be it white", "source": None, "months": [2], "date": None,
            "weather": ["rain", "snow"]}
OCTOBER = {"text": "October, cold and drab.", "source": "Spanish", "months": [10], "date": None, "weather": []}

FORECAST_RESPONSE = {
    "current": {"temperature_2m": 12.6, "weather_code": 61},
    "daily": {"weather_code": [63], "temperature_2m_max": [15.4], "temperature_2m_min": [-1.2],
              "precipitation_probability_max": [80], "wind_speed_10m_max": [31.0]},
}


@pytest.fixture(autouse=True)
def lore(monkeypatch):
    monkeypatch.setattr(weather, "LORE", [SWITHIN, CAT, FEBRUARY, OCTOBER])


# --- Open-Meteo ---
def test_parse_place():
    response = {"results": [{"name": "London", "admin1": "England", "country": "United Kingdom",
                             "latitude": 51.5, "longitude": -0.13}]}
    assert openmeteo.parse_place(response) == LONDON
    assert openmeteo.parse_place({"results": [{"name": "Monaco", "admin1": "Monaco", "country": "Monaco",
                                               "latitude": 43.7, "longitude": 7.4}]}).name == "Monaco"
    assert openmeteo.parse_place({}) is None and openmeteo.parse_place({"results": []}) is None


HIGHBRIDGES = {"results": [
    {"name": "Highbridge", "admin1": "England", "admin2": "Somerset", "admin3": "Sedgemoor District",
     "country": "United Kingdom", "country_code": "GB", "latitude": 51.22, "longitude": -2.98},
    {"name": "Highbridge", "admin1": "Idaho", "admin2": "Clark", "country": "United States", "country_code": "US",
     "latitude": 44.2, "longitude": -112.3},
    {"name": "Highbridge", "admin1": "England", "admin2": "Cumbria", "country": "United Kingdom", "country_code": "GB",
     "latitude": 54.8, "longitude": -2.9},
]}


def test_places_with_the_same_name():
    assert openmeteo.parse_place(HIGHBRIDGES).name == "Highbridge, Somerset, England, United Kingdom"  # likeliest
    assert openmeteo.parse_place(HIGHBRIDGES, ["Cumbria"]).latitude == 54.8
    assert openmeteo.parse_place(HIGHBRIDGES, ["idaho"]).name == "Highbridge, Clark, Idaho, United States"
    assert openmeteo.parse_place(HIGHBRIDGES, ["us"]).latitude == 44.2  # country code
    assert openmeteo.parse_place(HIGHBRIDGES, ["Narnia"]) is None


def test_parse_forecast_and_what_kind_of_day_it_is():
    forecast = openmeteo.parse_forecast(LONDON, FORECAST_RESPONSE)
    assert (forecast.now_c, forecast.high_c, forecast.low_c, forecast.rain_chance, forecast.wind_mph) == (
        12.6, 15.4, -1.2, 80, 31.0)
    assert forecast.kinds == {"rain", "frost", "wind"}
    assert openmeteo.parse_forecast(LONDON, {"current": {}}) is None


def test_kinds_of_weather():
    assert openmeteo.kinds_of_weather(0, 1, 28, 15, 0, 5) == {"clear", "hot", "dry"}
    assert openmeteo.kinds_of_weather(95, 95, 20, 10, 90, 10) == {"thunder", "storm", "rain"}
    assert openmeteo.kinds_of_weather(73, 71, 2, -3, 70, 10) == {"snow", "frost", "cold"}
    assert openmeteo.kinds_of_weather(3, 3, 12, 8, None, 5) == {"cloud", "dry"}


def test_unreachable_open_meteo_gives_none(monkeypatch):
    monkeypatch.setattr(openmeteo, "GEOCODE_URL", "http://127.0.0.1:1/search")
    monkeypatch.setattr(openmeteo, "FORECAST_URL", "http://127.0.0.1:1/forecast")
    openmeteo._places.clear()
    assert run(openmeteo.geocode("Nowhere")) is None
    assert run(openmeteo.forecast(LONDON)) is None
    assert "nowhere" not in openmeteo._places  # A failure isn't remembered


# --- Picking the saying ---
def test_a_saints_day_saying_on_its_day():
    assert weather.pick_saying({"clear"}, date(2026, 7, 15)) is SWITHIN


def test_a_saying_about_todays_weather_in_the_right_month():
    assert weather.pick_saying({"clear", "dry"}, date(2026, 10, 11)) is CAT
    assert weather.pick_saying({"snow"}, date(2026, 2, 3)) is FEBRUARY
    assert weather.pick_saying({"snow"}, date(2026, 10, 11)) is OCTOBER  # February's saying is out of season


def test_verdicts():
    assert weather.verdict(CAT, {"clear", "dry"}) in weather.AGREE
    assert weather.verdict(CAT, {"rain"}) in weather.DISAGREE
    assert weather.verdict(SWITHIN, {"clear", "dry"}) in weather.DISAGREE
    assert weather.verdict(OCTOBER, {"rain"}) in weather.UNSURE


def test_temperatures_in_both():
    assert weather.temperature(12.6) == "13°C (55°F)"
    assert weather.temperature(-1.2) == "-1°C (30°F)"


# --- The command ---
lookups: list[tuple[str, bool]] = []  # Every place looked up, and whether it was to be remembered
@pytest.fixture
def open_meteo(monkeypatch):
    places = {"london": LONDON, "highbridge": HIGHBRIDGE}
    lookups.clear()

    async def geocode(name, remember=True):
        lookups.append((name, remember))
        return places.get(name.casefold())

    async def forecast(place):
        return openmeteo.parse_forecast(place, FORECAST_RESPONSE)
    monkeypatch.setattr(openmeteo, "geocode", geocode)
    monkeypatch.setattr(openmeteo, "forecast", forecast)
    monkeypatch.setattr(config, "WEATHER_PLACE", "London")
    return places


def test_weather_command(open_meteo, monkeypatch):
    monkeypatch.setattr(weather.random, "choice", lambda options: options[0])
    ctx = Ctx(SCOTT)
    run(weather.weather_group.callback(ctx))
    embed = ctx.last.embed
    assert embed.title == "🌦️ London, England, United Kingdom"
    assert embed.description == ("🌦️ Now: 13°C (55°F), light rain\n"
                                 "🌧️ Today: rain, -1°C (30°F) to 15°C (60°F), 80% chance of rain, wind up to 31 mph")
    saying, view = embed.fields
    assert saying.name == "Meanwhile, in 1893"
    assert saying.value.startswith("> ")
    assert view.name == "The committee's view"
    assert embed.footer.text == "Forecast: Open-Meteo · Lore: Inwards' Weather Lore (1893)"


def test_a_verse_is_quoted_line_by_line():
    assert weather.saying_text(FEBRUARY) == "> February fill dyke,\n> Be it black or be it white\n-# Folk wisdom"
    assert weather.saying_text(OCTOBER).endswith("-# Folk wisdom (Spanish)")


def test_unknown_place(open_meteo):
    ctx = Ctx(SCOTT)
    run(weather.weather_group.callback(ctx, place="Xyzzy"))
    assert "can't find “Xyzzy”" in ctx.last.content


def test_open_meteo_down_still_gives_folk_wisdom(open_meteo):
    open_meteo.clear()  # Nothing can be found, not even London: Open-Meteo is down.
    ctx = Ctx(SCOTT)
    run(weather.weather_group.callback(ctx, place="Paris"))
    embed = ctx.last.embed
    assert embed.title == "🌦️ Paris" and "forecast's down" in embed.description
    assert embed.fields[0].name == "In 1893"


# --- Where you are, privately ---
def everything_public(ctx) -> str:
    """Every word posted where others can see it: not ephemeral replies, not DMs."""
    parts = []
    for sent in ctx.sent:
        if not sent.private:
            parts.append(sent.text)
    return "\n".join(parts)


def ask_where(user=SCOTT):
    """Run /weather here as a slash command: it answers with a form."""
    ctx = Ctx(user)
    ctx.interaction = Interaction(user)
    run(weather.weather_here.callback(ctx))
    return ctx


def test_slash_here_asks_in_a_form_not_an_option(open_meteo):
    # Discord shows a slash command's options to anyone hovering over "used /weather here": so it has none.
    assert [p.name for p in weather.weather_here.app_command.parameters] == []
    ctx = ask_where()
    form = ctx.interaction.modal
    assert isinstance(form, weather.WhereAreYou) and ctx.sent == []  # Nothing posted yet
    assert lookups == []


def test_your_weather_without_saying_where(open_meteo, caplog):
    caplog.set_level("DEBUG")
    form = ask_where().interaction.modal
    submitted = Interaction(SCOTT)
    form.place._value = "Highbridge"
    run(form.on_submit(submitted))
    assert submitted.deferred == {"thinking": True, "ephemeral": False}
    embed = submitted.last.embed
    assert embed.title == "🌦️ scott checked the weather where they are"
    assert embed.description.startswith("🌦️ Now: 13°C (55°F)") and embed.fields[0].name == "Meanwhile, in 1893"
    posted = "\n".join(sent.text for sent in submitted.sent)
    assert "Highbridge" not in posted and "Somerset" not in posted
    assert "Highbridge" not in caplog.text  # Never logged
    assert lookups == [("Highbridge", False)]  # Looked up without being remembered


def test_the_form_somewhere_that_isnt_on_the_map(open_meteo):
    form = ask_where().interaction.modal
    submitted = Interaction(SCOTT)
    form.place._value = "Xyzzy"
    run(form.on_submit(submitted))
    assert "couldn't find that" in submitted.last.content and "Xyzzy" not in submitted.last.content


def test_where_you_are_isnt_kept_anywhere(monkeypatch):
    """The real lookup, against a fake Open-Meteo: /weather here's place never goes in the cache."""
    async def fake_get(session, url, params):
        return {"results": [{"name": "Highbridge", "admin2": "Somerset", "admin1": "England",
                             "country": "United Kingdom", "latitude": 51.2, "longitude": -3.0}]}
    monkeypatch.setattr(openmeteo, "_get", fake_get)
    openmeteo._places.clear()
    assert run(openmeteo.geocode("Highbridge", remember=False)).name.startswith("Highbridge")
    assert openmeteo._places == {}
    run(openmeteo.geocode("London"))  # /weather in remembers places, which are public anyway
    assert list(openmeteo._places) == ["london"]


def test_nothing_about_places_is_stored():
    from ktdi import db
    tables = {row[0] for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not any("weather" in table or "place" in table for table in tables)


def typed_here(content):
    ctx = Ctx(SCOTT, slash=False, content=content)
    ctx.invoked_with = "here"
    run(weather.weather_here.callback(ctx))
    return ctx


def test_typed_here_deletes_the_message(open_meteo):
    ctx = typed_here("!weather here Highbridge")
    assert ctx.message.deleted
    assert ctx.last.embed.title == "🌦️ scott checked the weather where they are"
    assert "Highbridge" not in everything_public(ctx)
    assert lookups == [("Highbridge", False)]


def test_typed_here_without_a_place_or_somewhere_not_on_the_map(open_meteo):
    ctx = typed_here("!weather here")
    assert "Where?" in ctx.last.content and lookups == []
    ctx = typed_here("!weather here Xyzzy")
    assert ctx.message.deleted and "couldn't find that" in ctx.last.content and "Xyzzy" not in ctx.last.content


def test_weather_is_never_logged():
    from ktdi.bot import is_private_command
    for command in (weather.weather_group, weather.weather_here):
        assert is_private_command(types.SimpleNamespace(command=command)), command.qualified_name


def test_the_real_lore_file_is_well_formed():
    import json
    tags = {"rain", "snow", "frost", "hail", "thunder", "fog", "wind", "clear", "cloud", "hot", "cold", "dry", "storm"}
    lore = json.loads(weather.DATA.read_text(encoding="utf-8"))
    assert len(lore) >= 300
    for saying in lore:
        assert saying["text"].strip() and set(saying["weather"]) <= tags, saying
        assert all(1 <= m <= 12 for m in saying["months"]), saying
        if saying["date"]:
            month, day = map(int, saying["date"].split("-"))
            assert month in saying["months"] and date(2024, month, day), saying
