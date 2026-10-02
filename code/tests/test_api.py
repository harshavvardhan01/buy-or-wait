"""API contract tests. These run against the app in-process via TestClient -
no server needed, so they work in CI without a port."""
from decimal import Decimal

import pytest
from api.app import app
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(scope="module")
def sample_payload():
    response = client.get("/api/samples/request_12")
    assert response.status_code == 200
    return response.json()


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_samples_list_has_all_solved_cases():
    rows = client.get("/api/samples").json()
    assert len(rows) == 25
    assert all("expected_status" in row for row in rows)


def test_sample_payload_round_trips(sample_payload):
    """A payload fetched from /api/samples must be accepted by /api/analyze
    unchanged. If this breaks, the two schemas have drifted apart."""
    response = client.post("/api/analyze", json=sample_payload)
    assert response.status_code == 200, response.text


def test_request_12_matches_the_engine(sample_payload):
    """request_12 is the case where per-event income filtering mattered:
    seasonal contract pay projects, so the installment plan clears."""
    body = client.post("/api/analyze", json=sample_payload).json()
    decision = body["decision"]

    assert decision["affordability_status"] == "affordable_with_plan"
    assert decision["recommended_payment_method"] == "installments"
    assert len(decision["payment_plan"]) == 3
    assert Decimal(decision["amount_safe_to_pay"]) == Decimal("65164")


def test_projection_covers_the_full_horizon(sample_payload):
    projection = client.post("/api/analyze", json=sample_payload).json()["projection"]
    assert len(projection["points"]) == 91          # day 0 through day 90
    assert projection["points"][0]["date"] == sample_payload["request"]["request_date"]
    balances = [Decimal(p["balance"]) for p in projection["points"]]
    assert Decimal(projection["trough_balance"]) == min(balances)


def test_reasoning_exposes_the_engine_internals(sample_payload):
    reasoning = client.post("/api/analyze", json=sample_payload).json()["reasoning"]
    assert reasoning["detected_series"]
    assert isinstance(reasoning["rejected_plans"], list)
    assert isinstance(reasoning["income_projected"], bool)


def test_editing_the_profile_changes_the_answer(sample_payload):
    """The point of a stateless API: raise the minimum balance and the same
    request should become less affordable. This is what the frontend sliders
    will exercise."""
    baseline = client.post("/api/analyze", json=sample_payload).json()

    tightened = {**sample_payload,
                 "profile": {**sample_payload["profile"],
                             "minimum_balance_to_keep": "150000"}}
    strained = client.post("/api/analyze", json=tightened).json()

    assert (Decimal(strained["decision"]["amount_safe_to_pay"])
            < Decimal(baseline["decision"]["amount_safe_to_pay"]))


def test_unknown_request_returns_404():
    assert client.get("/api/samples/request_9999").status_code == 404

def test_money_is_two_decimal_places(sample_payload):
    body = client.post("/api/analyze", json=sample_payload).json()
    for point in body["projection"]["points"]:
        assert round(point["balance"], 2) == point["balance"]
    for series in body["reasoning"]["detected_series"]:
        assert round(series["monthly_equivalent"], 2) == series["monthly_equivalent"]


def test_weekly_resolution_keeps_the_trough(sample_payload):
    daily = client.post("/api/analyze", json=sample_payload).json()["projection"]
    weekly = client.post("/api/analyze",
                         json={**sample_payload, "resolution": "weekly"}
                         ).json()["projection"]
    assert len(weekly["points"]) < len(daily["points"])
    assert weekly["trough_date"] == daily["trough_date"]
    assert min(p["balance"] for p in weekly["points"]) == weekly["trough_balance"]


def test_batch_matches_individual_calls(sample_payload):
    single = client.post("/api/analyze", json=sample_payload).json()
    batch = client.post("/api/analyze/batch", json=[sample_payload, sample_payload]).json()
    assert len(batch) == 2
    assert batch[0]["decision"] == single["decision"]

def test_accuracy_reports_the_known_baseline():
    """Guards against silent regression: these numbers were measured, and a
    change to the engine that moves them should fail loudly here."""
    body = client.get("/api/accuracy").json()
    assert body["total"] == 25
    assert body["status_correct"] >= 18
    assert body["method_correct"] >= 19
    assert body["median_relative_error"] < 0.15


def test_accuracy_rows_are_self_consistent():
    for row in client.get("/api/accuracy").json()["rows"]:
        assert row["status_match"] == (
            row["predicted_status"] == row["expected_status"])
        assert row["relative_error"] >= 0