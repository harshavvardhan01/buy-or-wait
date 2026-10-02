"""Load every dataset file once, return plain dataframes."""
import pandas as pd

from config import DATASET


def _read(name: str) -> pd.DataFrame:
    """Everything loads as strings with NA disabled on purpose.

    Pandas would otherwise coerce the 16 deliberately-blank amounts to NaN and
    the string "false" to a bool. Both conversions are decisions the domain
    layer should make explicitly - a blank amount is a signal to read an image,
    not missing data.
    """
    return pd.read_csv(DATASET / name, dtype=str, keep_default_na=False)


def load_all() -> dict[str, pd.DataFrame]:
    return {
        "requests": _read("requests.csv"),
        "samples": _read("sample_requests.csv"),
        "profiles": _read("financial_profiles.csv"),
        "events": _read("financial_events.csv"),
        "options": _read("request_payment_options.csv"),
        "messages": _read("messages.csv"),
        "images": _read("images.csv"),
        "rates": _read("exchange_rates.csv"),
    }   