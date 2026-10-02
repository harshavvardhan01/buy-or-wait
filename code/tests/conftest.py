"""Shared fixtures. Loads the dataset once per session - reading 25k events
per test would make the suite too slow to run on every save."""
import sys
from pathlib import Path

import pytest

CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))

from io_load import load_all  # noqa: E402
from money import RateTable  # noqa: E402
from vision import resolve_amounts  # noqa: E402


@pytest.fixture(scope="session")
def data():
    return load_all()


@pytest.fixture(scope="session")
def rates(data):
    return RateTable(data["rates"])


@pytest.fixture(scope="session")
def profiles(data):
    return {row["user_id"]: row for row in data["profiles"].to_dict("records")}


@pytest.fixture(scope="session")
def events_by_user(data):
    grouped = {}
    for row in data["events"].to_dict("records"):
        grouped.setdefault(row["user_id"], []).append(row)
    return grouped


@pytest.fixture(scope="session")
def options_by_request(data):
    grouped = {}
    for row in data["options"].to_dict("records"):
        grouped.setdefault(row["request_id"], []).append(row)
    return grouped


@pytest.fixture(scope="session")
def image_amounts(data):
    link = dict(zip(data["images"]["related_event_id"],
                    data["images"]["image_id"], strict=True))
    blanks = [{"event_id": r["event_id"], "image_id": link[r["event_id"]],
               "description": r["description"], "category": r["category"],
               "direction": r["direction"], "currency": r["currency"],
               "event_date": r["event_date"]}
              for r in data["events"].to_dict("records")
              if r["amount"] == "" and r["event_id"] in link]
    # use_llm=False keeps the suite offline and free; the cache is already warm.
    return resolve_amounts(blanks, use_llm=False)