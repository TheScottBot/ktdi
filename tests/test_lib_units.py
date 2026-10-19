"""Unit conversions for /abm and /imperial (ktdi.lib.abm)."""

import pytest

from ktdi.lib import abm


@pytest.mark.parametrize("text, dimension, si_value", [
    ("3cm", "length", 0.03), ("2.5 kg", "mass", 2.5), ("500ml", "volume", 0.0005), ("1,000 m", "length", 1000),
    ("100 km/h", "speed", 100 / 3.6), ("3mW", "power", 0.003), ("3MW", "power", 3_000_000),
])
def test_parse(text, dimension, si_value):
    _, parsed_dimension, parsed_value = abm.parse(text)
    assert parsed_dimension == dimension
    assert parsed_value == pytest.approx(si_value)


def test_parse_temperature_to_kelvin():
    assert abm.parse("20C")[2] == pytest.approx(293.15)
    assert abm.parse("32F")[2] == pytest.approx(273.15)


@pytest.mark.parametrize("text", ["banana", "3 furlongs"])
def test_parse_errors(text):
    with pytest.raises(abm.ABMError):
        abm.parse(text)


def test_abm_always_gives_an_answer():
    for text in ["3cm", "20C", "75kg", "1.5l", "85dB", "1km", "90min", "2kW"]:
        assert text in abm.convert(text)


def test_abm_has_no_jabs_at_imperial():
    for _ in range(50):
        reply = abm.convert("100F")
        assert "freedom" not in reply and "Bold" not in reply


@pytest.mark.parametrize("text, expected", [
    ("3cm", "1.18 in"),
    ("180cm", "5 ft 10.9 in (5.91 ft)"),
    ("182.88 cm", "6 ft"),
    ("75kg", "165.3 lb (11 st 11.3 lb)"),
    ("1l", "2.11 US pints (1.76 UK pints)"),
    ("20C", "68 °F"),
    ("100km/h", "62.14 mph"),
    ("2000kcal", "7,931 BTU (2,000 food Calories)"),
])
def test_imperial(text, expected):
    reply = abm.to_imperial(text)
    assert expected in reply
    assert reply.endswith("❤️")


def test_imperial_already_fahrenheit():
    assert "37.8 °C" in abm.to_imperial("100F")


def test_unit_help_lists_every_dimension():
    names = [name for name, _ in abm.input_unit_help()]
    assert len(names) == 12 and any("Length" in n for n in names)


# --- /metric: /imperial the other way round ---
@pytest.mark.parametrize("text, expected", [
    ("5ft 10", "1.78 m (177.8 cm)"),
    ("5'10\"", "1.78 m (177.8 cm)"),
    ("5 ft 10 in", "1.78 m (177.8 cm)"),
    ("5ft2", "1.57 m (157.5 cm)"),  # A height, not square feet
    ("11st 4lb", "71.67 kg"),
    ("11 stone 4", "71.67 kg"),
    ("2 lb 3 oz", "992.2 g"),
    ("12 in", "30.48 cm"),
    ("26.2 miles", "42.16 km"),
    ("2 cups", "473.2 ml"),
    ("1 US pint", "473.2 ml"),
    ("1 imperial gallon", "4.55 L"),
    ("70F", "21.1 °C"),
    ("-40F", "-40 °C"),
    ("60 mph", "96.56 km/h (26.82 m/s)"),
    ("32 psi", "220.6 kPa (2.21 bar)"),
    ("29.92 inHg", "1,013 hPa"),
    ("300 hp", "223.7 kW"),
    ("1000 sq ft", "92.9 m²"),
    ("2000 Cal", "8,368 kJ (2,000 kcal)"),
    ("1 short ton", "907.2 kg"),
])
def test_metric(text, expected):
    reply = abm.to_metric(text)
    assert f"{text} = **{expected}" in reply and reply.endswith("❤️")


def test_metric_gives_both_when_the_uk_and_us_differ():
    assert abm.to_metric("1 pint") == "🪣 1 pint = **568.3 ml** (UK) or **473.2 ml** (US) ❤️"
    assert "**1.02 tonnes (1,016 kg)** (UK) or **907.2 kg** (US)" in abm.to_metric("1 ton")


def test_metric_of_something_already_metric():
    assert abm.to_metric("3cm") == "📏 3cm is already metric. In imperial it's **1.18 in**. ❤️"
    assert "68 °F" in abm.to_metric("20C")
    assert "the same everywhere" in abm.to_metric("90min")


@pytest.mark.parametrize("text", ["banana", "5 ft 10 lb", "1 2 3 ft", "pint"])
def test_metric_errors(text):
    with pytest.raises(abm.ABMError, match="imperial or US unit"):
        abm.to_metric(text)


def test_metric_never_jabs():
    for text in ["70F", "1 pint", "5ft 10", "3cm"]:
        reply = abm.to_metric(text).lower()
        assert not any(word in reply for word in ("freedom", "silly", "weird", "bold", "sensible"))


def test_metric_unit_help_lists_every_dimension():
    names = [name for name, _ in abm.metric_unit_help()]
    assert len(names) == 10 and any("Temperature" in n for n in names)
