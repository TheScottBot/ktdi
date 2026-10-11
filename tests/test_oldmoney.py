"""Old British money in today's money, for Mrs Beeton's costs (ktdi.lib.oldmoney)."""

from ktdi.lib import oldmoney


def test_reading_old_money():
    assert [p for _, _, p in oldmoney.amounts("2s. 3d. per quart")] == [27]  # 12d to the shilling
    assert [p for _, _, p in oldmoney.amounts("1-1/2d. each slice")] == [1.5]
    assert [p for _, _, p in oldmoney.amounts("1/2d")] == [0.5]
    assert [p for _, _, p in oldmoney.amounts("£1 1s")] == [252]  # 240d to the pound
    assert [p for _, _, p in oldmoney.amounts("1s, 6d., exclusive of the cold meat")] == [18]
    assert [p for _, _, p in oldmoney.amounts("8-1/2 d. per lb")] == [8.5]  # A space before the d
    assert oldmoney.amounts("Seldom bought") == [] and oldmoney.amounts("1-1/2 lb. of beef") == []
    assert oldmoney.amounts("9 dozen eggs, 2 slices") == []  # Not money


def test_todays_money_is_rounded_to_what_matters():
    assert oldmoney.today(6) == "£3.90"  # 6d: under £10, to 10p
    assert oldmoney.today(27) == "£17"  # 2s. 3d: under £100, to the pound
    assert oldmoney.today(480) == "£310"  # £2: to £10


def test_costs_in_todays_money():
    assert oldmoney.in_todays_money("2s. 3d. per quart") == "2s. 3d. per quart (about £17 now)"
    assert oldmoney.in_todays_money("for this quantity, 6d") == "for this quantity, 6d (about £3.90 now)"
    assert oldmoney.in_todays_money("from 6d. to 8d. per lb. pot") == \
        "from 6d. to 8d. per lb. pot (about £3.90–£5.20 now)"  # A range
    assert oldmoney.in_todays_money("with cream at 1s. per pint, 2s. 3d") == \
        "with cream at 1s. (about £7.80) per pint, 2s. 3d (about £17)"  # Separate sums, each its own
    assert oldmoney.in_todays_money("2s. 3d. or 1s. 9d. per quart") == \
        "2s. 3d. (about £17) or 1s. 9d. (about £14) per quart"
    assert oldmoney.in_todays_money("Seldom bought") == "Seldom bought"  # No money, left alone
