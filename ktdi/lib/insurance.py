"""The committee's two clocks, for /insurance. Deliberately predictable: no randomness and no secrets.

A policy's length comes from the policyholder's Discord ID and the UTC minute it was bought (00-59, its tens and ones
digits taken separately), so the same person buying at the same minute always gets the same cover. Anyone can read
this and work out their best (or someone else's worst) minute to buy. That's the game, not a bug.

The microwave clock is the real cover: it decides every claim. The car clock is the countdown customers are shown.
It's the microwave's time give or take up to 20%, and either can run out first. Both stay within 2:00-9:59.
"""

SHORTEST = 120  # 2:00
LONGEST = 599  # 9:59
MAX_ERROR = 20  # The car clock is off by up to this many % of the real cover.


def id_digits(user_id: int) -> list[int]:
    """The ID's digits, padded to 19 (the longest Discord ID) so short ones still have every position."""
    return [int(d) for d in str(user_id).zfill(19)]


def microwave_clock(user_id: int, minute: int) -> int:
    """Seconds of real cover."""
    d = id_digits(user_id)
    tens, ones = divmod(minute, 10)
    seed = 3 * d[-1] + 5 * d[-4] + 7 * d[-7] + 11 * d[-10]
    return SHORTEST + (13 * seed + 137 * tens + 83 * ones + 71 * tens * ones + 19 * tens * tens
                       + 23 * ones * ones) % (LONGEST + 1 - SHORTEST)


def clock_error(user_id: int, minute: int) -> int:
    """How far off the car clock is, in % (-20 to 20)."""
    d = id_digits(user_id)
    tens, ones = divmod(minute, 10)
    seed = 11 * d[-2] + 7 * d[-5] + 5 * d[-8] + 3 * d[-11]
    return (17 * seed + 31 * tens + 37 * ones + 11 * tens * ones + 3 * tens * tens + 7 * ones * ones) \
        % (2 * MAX_ERROR + 1) - MAX_ERROR


def car_clock(user_id: int, minute: int) -> int:
    """Seconds of cover the customer is shown."""
    shown = round(microwave_clock(user_id, minute) * (100 + clock_error(user_id, minute)) / 100)
    return max(SHORTEST, min(LONGEST, shown))


def clocks(user_id: int, minute: int) -> tuple[int, int]:
    """(microwave, car): the real cover and the cover shown, in seconds."""
    return microwave_clock(user_id, minute), car_clock(user_id, minute)
