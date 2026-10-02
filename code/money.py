"""Money and FX. All amounts become Decimal in the user's home currency here."""
from decimal import Decimal, InvalidOperation


def to_decimal(raw):
    """Parse a CSV money string. Returns None for blank - NEVER zero.

    The spec is explicit that a blank amount is a signal to look at an image,
    not a zero. Returning None forces every caller to handle it deliberately.
    """
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if text == "":
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


class RateTable:
    """Dated FX lookup. Keyed on (rate_date, from_currency, to_currency)."""

    def __init__(self, rates_df):
        # `self._rates` is a plain dict rather than a dataframe query because
        # this is hit ~140 times per full run inside tight loops.
        self._rates = {
            (row["rate_date"], row["from_currency"], row["to_currency"]):
                Decimal(row["rate"])
            for _, row in rates_df.iterrows()
        }

    def convert(self, amount, from_ccy, to_ccy, on_date):
        if amount is None or from_ccy == to_ccy:
            return amount
        rate = self._rates.get((on_date, from_ccy, to_ccy))
        if rate is None:
            raise KeyError(f"no rate {from_ccy}->{to_ccy} on {on_date}")
        return amount * rate