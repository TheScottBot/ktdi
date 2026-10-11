"""Roman numerals (ktdi.lib.roman)."""

import pytest

from ktdi.lib import roman


@pytest.mark.parametrize("numeral, number", [("I", 1), ("IV", 4), ("VIII", 8), ("IX", 9), ("XIX", 19),
                                             ("XXXVII", 37), ("XL", 40), ("xc", 90), ("CIV", 104)])
def test_to_int(numeral, number):
    assert roman.to_int(numeral) == number
