"""FastAPI surface. Run with:  uvicorn api.app:app --reload --app-dir code"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from decimal import Decimal  # noqa: E402

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from io_load import load_all  # noqa: E402
from money import RateTable  # noqa: E402
from vision import resolve_amounts  # noqa: E402

from .models import (  # noqa: E402
    AccuracyRow,
    AccuracySummary,
    AnalyzeRequest,
    AnalyzeResponse,
)
from .service import analyze  # noqa: E402

app = FastAPI(title="Buy or Wait?",
              description="Deterministic affordability engine over a 90-day "
                          "daily cash-flow projection.",
              version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def _dataset():
    """Loaded once and cached. 25k event rows would otherwise be re-parsed on
    every sample request."""
    data = load_all()
    return data, RateTable(data["rates"])


@lru_cache(maxsize=1)
def _image_amounts() -> dict:
    data, _ = _dataset()
    link = dict(zip(data["images"]["related_event_id"],
                    data["images"]["image_id"], strict=True))
    blanks = [{"event_id": r["event_id"], "image_id": link[r["event_id"]],
               "description": r["description"], "category": r["category"],
               "direction": r["direction"], "currency": r["currency"],
               "event_date": r["event_date"]}
              for r in data["events"].to_dict("records")
              if r["amount"] == "" and r["event_id"] in link]
    return resolve_amounts(blanks, use_llm=False)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/samples")
def list_samples() -> list[dict]:
    """The 25 solved cases, for the frontend to load as starting points."""
    data, _ = _dataset()
    return [
        {"request_id": r["request_id"], "user_id": r["user_id"],
         "request_type": r["request_type"], "requested_amount": r["requested_amount"],
         "request_date": r["request_date"], "currency": _currency(data, r["user_id"]),
         "expected_status": r["affordability_status"],
         "expected_method": r["recommended_payment_method"]}
        for r in data["samples"].to_dict("records")]


def _currency(data, user_id: str) -> str:
    row = data["profiles"][data["profiles"]["user_id"] == user_id]
    return row.iloc[0]["home_currency"] if len(row) else ""


@app.get("/api/samples/{request_id}", response_model=AnalyzeRequest)
def get_sample(request_id: str) -> AnalyzeRequest:
    """Rebuild a full analyze payload from the dataset, so the frontend can
    load a realistic case and then let the user edit it."""
    data, _ = _dataset()
    source = data["samples"]
    match = source[source["request_id"] == request_id]
    if not len(match):
        source = data["requests"]
        match = source[source["request_id"] == request_id]
    if not len(match):
        raise HTTPException(404, f"unknown request {request_id}")

    row = match.iloc[0].to_dict()
    profile = data["profiles"][
        data["profiles"]["user_id"] == row["user_id"]].iloc[0].to_dict()
    events = data["events"][
        data["events"]["user_id"] == row["user_id"]].to_dict("records")
    options = data["options"][
        data["options"]["request_id"] == request_id].to_dict("records")

    return AnalyzeRequest.model_validate({
        "profile": {
            "user_id": profile["user_id"],
            "home_currency": profile["home_currency"],
            "current_available_balance": profile["current_available_balance"],
            "minimum_balance_to_keep": profile["minimum_balance_to_keep"],
            "financial_priorities": _split(profile["financial_priorities"]),
            "expense_categories_to_protect":
                _split(profile["expense_categories_to_protect"]),
            "expense_categories_user_is_willing_to_reduce":
                _split(profile["expense_categories_user_is_willing_to_reduce"]),
            "expense_categories_user_is_willing_to_stop":
                _split(profile["expense_categories_user_is_willing_to_stop"]),
            "payment_methods_user_will_consider":
                _split(profile["payment_methods_user_will_consider"]),
            "max_installment_months":
                profile["max_installment_months"] or None,
        },
        "events": [_event_payload(e) for e in events],
        "payment_options": [_option_payload(o) for o in options],
        "request": {
            "request_id": row["request_id"],
            "request_date": row["request_date"],
            "request_type": row["request_type"],
            "requested_amount": row["requested_amount"],
            "desired_completion_date": row["desired_completion_date"] or None,
            "allows_partial_payment":
                str(row["allows_partial_payment"]).lower() == "true",
            "request_text": row.get("request_text", ""),
        },
    })


def _split(text: str) -> list[str]:
    return [p.strip() for p in str(text).split("|") if p.strip()]


def _event_payload(row: dict) -> dict:
    return {
        "event_id": row["event_id"], "event_type": row["event_type"],
        "description": row["description"], "category": row["category"],
        "direction": row["direction"],
        "amount": row["amount"] or None, "currency": row["currency"],
        "event_date": row["event_date"],
        "settlement_date": row["settlement_date"] or None,
        "status": row["status"], "flexibility": row["flexibility"],
        "minimum_allowed_amount": row["minimum_allowed_amount"] or None,
        "linked_event_id": row["linked_event_id"],
    }


def _option_payload(row: dict) -> dict:
    return {
        "payment_option_id": row["payment_option_id"],
        "payment_method": row["payment_method"],
        "payment_amount": row["payment_amount"],
        "number_of_payments": row["number_of_payments"] or 1,
        "first_payment_date": row["first_payment_date"] or None,
        "payment_frequency_days": row["payment_frequency_days"] or None,
        "financing_fee": row["financing_fee"] or 0,
        "total_payable_amount": row["total_payable_amount"] or None,
    }


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze_request(payload: AnalyzeRequest) -> AnalyzeResponse:
    _, rates = _dataset()
    return analyze(payload, rates, _image_amounts())

@app.post("/api/analyze/batch", response_model=list[AnalyzeResponse])
def analyze_batch(payloads: list[AnalyzeRequest]) -> list[AnalyzeResponse]:
    """Sequential rather than concurrent: the engine is pure CPU work with no
    I/O to overlap, so threads would add contention without throughput."""
    _, rates = _dataset()
    images = _image_amounts()
    return [analyze(payload, rates, images) for payload in payloads]

@app.get("/api/accuracy", response_model=AccuracySummary)
def accuracy() -> AccuracySummary:
    """Score the engine against the 25 solved samples.

    Runs the real pipeline, not a cached result file: if the engine regresses,
    this endpoint shows it immediately.
    """
    data, rates = _dataset()
    images = _image_amounts()
    rows: list[AccuracyRow] = []

    for sample in data["samples"].to_dict("records"):
        request_id = sample["request_id"]
        payload = get_sample(request_id)
        result = analyze(payload, rates, images)

        expected_amount = Decimal(sample["amount_safe_to_pay"])
        predicted_amount = Decimal(str(result.decision.amount_safe_to_pay))
        # Guard the denominator: a ground-truth zero would otherwise divide by
        # zero, and an absolute error against zero is the honest comparison.
        denominator = max(expected_amount, Decimal(1))
        error = abs(predicted_amount - expected_amount) / denominator

        rows.append(AccuracyRow(
            request_id=request_id,
            user_id=sample["user_id"],
            request_type=sample["request_type"],
            currency=payload.profile.home_currency,
            requested_amount=Decimal(sample["requested_amount"]),
            expected_status=sample["affordability_status"],
            predicted_status=result.decision.affordability_status,
            status_match=(result.decision.affordability_status
                          == sample["affordability_status"]),
            expected_method=sample["recommended_payment_method"],
            predicted_method=result.decision.recommended_payment_method,
            method_match=(result.decision.recommended_payment_method
                          == sample["recommended_payment_method"]),
            expected_amount=expected_amount,
            predicted_amount=predicted_amount,
            relative_error=float(error),
            rejections=result.reasoning.rejected_plans,
        ))

    errors = sorted(row.relative_error for row in rows)
    return AccuracySummary(
        total=len(rows),
        status_correct=sum(1 for r in rows if r.status_match),
        method_correct=sum(1 for r in rows if r.method_match),
        amount_within_2pct=sum(1 for e in errors if e < 0.02),
        amount_within_10pct=sum(1 for e in errors if e < 0.10),
        median_relative_error=errors[len(errors) // 2] if errors else 0.0,
        rows=rows,
    )

