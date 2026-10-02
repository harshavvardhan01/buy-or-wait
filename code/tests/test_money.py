"""Money parsing and FX conversion."""
from decimal import Decimal

import pytest

from money import to_decimal


def test_blank_amount_is_none_not_zero():
    """The spec treats a blank amount as a signal to read an image. Returning
    zero would silently erase a real expense from the forecast."""
    assert to_decimal("") is None
    assert to_decimal(None) is None


@pytest.mark.parametrize("raw,expected", [
    ("1234.56", Decimal("1234.56")),
    ("1,234.56", Decimal("1234.56")),
    ("  99 ", Decimal("99")),
    ("0", Decimal("0")),
])
def test_money_parsing(raw, expected):
    assert to_decimal(raw) == expected


def test_garbage_returns_none(): 
    assert to_decimal("not-a-number") is None


def test_fx_direct_pair(rates):
    """Every foreign event in the dataset resolves on a direct pair lookup."""
    converted = rates.convert(Decimal("1800"), "USD", "IDR", "2024-03-15")
    assert converted == Decimal("1800") * rates._rates[("2024-03-15", "USD", "IDR")]


def test_fx_same_currency_is_identity(rates):
    assert rates.convert(Decimal("500"), "EUR", "EUR", "2024-03-15") == Decimal("500")


def test_fx_missing_rate_raises(rates):
    """Fail loudly rather than silently substituting an inverse or 1.0."""
    with pytest.raises(KeyError):
        rates.convert(Decimal("100"), "GBP", "JPY", "2024-03-15")