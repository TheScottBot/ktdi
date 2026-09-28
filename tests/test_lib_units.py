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
