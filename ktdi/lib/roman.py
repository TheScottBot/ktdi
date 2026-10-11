"""Roman numerals, as old books number their books and chapters."""

VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def to_int(numeral: str) -> int:
    """"VIII" is 8, "XIX" is 19, "XXXVII" is 37."""
    values = [VALUES[letter] for letter in numeral.upper()]
    return sum(-v if i + 1 < len(values) and v < values[i + 1] else v for i, v in enumerate(values))
