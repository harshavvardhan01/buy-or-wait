"""End-to-end invariants over the full 250-request run."""
import csv
from decimal import Decimal

import pytest

import config
from schema import OUTPUT_COLUMNS


@pytest.fixture(scope="module")
def output_rows():
    if not config.OUTPUT.exists():
        pytest.skip("run `python code/main.py` first")
    with open(config.OUTPUT, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_schema_is_exact(output_rows):
    assert tuple(output_rows[0].keys()) == OUTPUT_COLUMNS


def test_one_row_per_request(output_rows, data):
    assert len(output_rows) == len(data["requests"])
    assert ({r["request_id"] for r in output_rows}
            == set(data["requests"]["request_id"]))


def test_amounts_within_bounds(output_rows, data):
    requested = dict(zip(data["requests"]["request_id"],
                         data["requests"]["requested_amount"], strict=True))
    for row in output_rows:
        amount = Decimal(row["amount_safe_to_pay"])
        assert 0 <= amount <= Decimal(requested[row["request_id"]])


def test_enums_are_valid(output_rows):
    for row in output_rows:
        assert row["affordability_status"] in config.ALL_STATUSES
        assert row["recommended_payment_method"] in config.ALL_METHODS


def test_not_affordable_rows_are_fully_blank(output_rows):
    for row in output_rows:
        if row["affordability_status"] == config.STATUS_NOT:
            assert row["earliest_date_for_full_payment"] == ""
            assert row["payment_plan"] == config.NONE_TOKEN
            assert row["recommended_payment_method"] == config.METHOD_NONE


def test_affordable_now_pays_on_the_request_date(output_rows, data):
    dates = dict(zip(data["requests"]["request_id"],
                     data["requests"]["request_date"], strict=True))
    for row in output_rows:
        if row["affordability_status"] == config.STATUS_NOW:
            assert row["earliest_date_for_full_payment"] == dates[row["request_id"]]


def test_payment_plans_parse_and_are_chronological(output_rows):
    for row in output_rows:
        if row["payment_plan"] == config.NONE_TOKEN:
            continue
        parts = row["payment_plan"].split("|")
        dates = [p.split(":")[0] for p in parts]
        assert dates == sorted(dates)
        for part in parts:
            _, amount = part.split(":")
            assert Decimal(amount) > 0


def test_every_row_has_an_explanation(output_rows):
    for row in output_rows:
        assert len(row["decision_explanation"]) > 20