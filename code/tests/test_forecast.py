"""Forecast arithmetic. These are pure functions over a balance array, so they
are tested against hand-computed values rather than dataset rows."""
from datetime import date
from decimal import Decimal

import forecast

RD = date(2026, 1, 1)


def _curve(values):
    return [Decimal(str(v)) for v in values]


def test_headroom_is_distance_from_the_trough():
    balance = _curve([1000, 900, 700, 1200])
    assert forecast.headroom(balance, Decimal("500")) == Decimal("200")


def test_safe_today_is_capped_at_requested():
    balance = _curve([1000, 900, 800])
    assert forecast.safe_today(balance, Decimal("100"), Decimal("250")) == Decimal("250")


def test_safe_today_never_negative():
    balance = _curve([100, 50])
    assert forecast.safe_today(balance, Decimal("500"), Decimal("250")) == Decimal("0")


def test_earliest_full_payment_uses_suffix_minimum():
    """Day 1's trough is behind us by day 2, so day 2 is the first safe date
    even though the overall minimum is lower."""
    balance = _curve([500, 200, 900, 900, 900])
    got = forecast.earliest_full_payment(balance, Decimal("100"),
                                         Decimal("700"), RD)
    assert got == date(2026, 1, 3)       # index 2


def test_earliest_full_payment_none_when_never_safe():
    balance = _curve([100, 100, 100])
    assert forecast.earliest_full_payment(
        balance, Decimal("50"), Decimal("500"), RD) is None


def test_earliest_is_request_date_when_already_affordable():
    balance = _curve([1000, 1000, 1000])
    assert forecast.earliest_full_payment(
        balance, Decimal("100"), Decimal("200"), RD) == RD


# --- monotonicity: the properties that prove nothing is memorised ---

def test_raising_minimum_balance_never_raises_safe_amount():
    balance = _curve([1000, 800, 900])
    requested = Decimal("1000")
    previous = None
    for minimum in [Decimal(m) for m in (0, 100, 300, 500, 800)]:
        current = forecast.safe_today(balance, minimum, requested)
        if previous is not None:
            assert current <= previous
        previous = current


def test_raising_requested_never_lowers_safe_amount():
    """safe_today is min(headroom, requested), so a larger request can only
    lift the cap - never reduce what is actually safe."""
    balance = _curve([1000, 800, 900])
    minimum = Decimal("200")
    previous = None
    for requested in [Decimal(r) for r in (100, 400, 600, 5000)]:
        current = forecast.safe_today(balance, minimum, requested)
        if previous is not None:
            assert current >= previous
        previous = current


def test_raising_balance_never_lowers_safe_amount():
    minimum, requested = Decimal("200"), Decimal("10000")
    previous = None
    for lift in (0, 100, 500, 2000):
        balance = _curve([1000 + lift, 800 + lift, 900 + lift])
        current = forecast.safe_today(balance, minimum, requested)
        if previous is not None:
            assert current >= previous
        previous = current