"""Wire format. These mirror the CSV columns rather than the engine's internal
dataclasses, so the API contract stays stable if the engine is refactored."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer

# Decimal serializes as a JSON string by default, which would make every amount
# a `string` in the generated TypeScript. Emitting a float keeps the frontend
# types honest; precision is already fixed at 2dp by the time values get here.
Money = Annotated[Decimal, PlainSerializer(float, return_type=float)]

class EventIn(BaseModel):
    event_id: str
    event_type: str
    description: str = ""
    category: str = ""
    direction: str                      # debit | credit | non_cash
    amount: Decimal | None = None       # None means "read it from an image"
    currency: str
    event_date: date
    settlement_date: date | None = None
    status: str = "settled"
    flexibility: str = "fixed"
    minimum_allowed_amount: Decimal | None = None
    linked_event_id: str = ""


class ProfileIn(BaseModel):
    user_id: str = "user"
    home_currency: str
    current_available_balance: Decimal
    minimum_balance_to_keep: Decimal
    financial_priorities: list[str] = Field(default_factory=list)
    expense_categories_to_protect: list[str] = Field(default_factory=list)
    expense_categories_user_is_willing_to_reduce: list[str] = Field(default_factory=list)
    expense_categories_user_is_willing_to_stop: list[str] = Field(default_factory=list)
    payment_methods_user_will_consider: list[str] = Field(default_factory=list)
    max_installment_months: int | None = None


class PaymentOptionIn(BaseModel):
    payment_option_id: str
    payment_method: str
    payment_amount: Decimal
    number_of_payments: int = 1
    first_payment_date: date | None = None
    payment_frequency_days: int | None = None
    financing_fee: Decimal = Decimal(0)
    total_payable_amount: Decimal | None = None


class RequestIn(BaseModel):
    request_id: str = "request"
    request_date: date
    request_type: str = "purchase"
    requested_amount: Decimal
    desired_completion_date: date | None = None
    allows_partial_payment: bool = False
    request_text: str = ""


class AnalyzeRequest(BaseModel):
    profile: ProfileIn
    events: list[EventIn]
    payment_options: list[PaymentOptionIn] = Field(default_factory=list)
    request: RequestIn
    resolution: str = "daily"           # daily | weekly


class PaymentOut(BaseModel):
    date: date
    amount: Money


class DecisionOut(BaseModel):
    amount_safe_to_pay: Money
    affordability_status: str
    recommended_payment_method: str
    payment_plan: list[PaymentOut]
    earliest_date_for_full_payment: date | None
    spending_changes_needed: list[str]
    decision_explanation: str


class ProjectionPoint(BaseModel):
    date: date
    balance: Money


class ProjectionOut(BaseModel):
    points: list[ProjectionPoint]
    minimum_balance: Money
    trough_date: date
    trough_balance: Money
    headroom: Money


class SeriesOut(BaseModel):
    category: str
    direction: str
    period_days: int
    amount: Money
    monthly_equivalent: Money
    last_seen: date
    flexibility: str
    occurrences: int

class ReasoningOut(BaseModel):
    detected_series: list[SeriesOut]
    confirmed_future_events: list[EventIn]
    rejected_plans: list[str]
    income_projected: bool


class AnalyzeResponse(BaseModel):
    decision: DecisionOut
    projection: ProjectionOut
    reasoning: ReasoningOut

class AccuracyRow(BaseModel):
    request_id: str
    user_id: str
    request_type: str
    currency: str
    requested_amount: Money

    expected_status: str
    predicted_status: str
    status_match: bool

    expected_method: str
    predicted_method: str
    method_match: bool

    expected_amount: Money
    predicted_amount: Money
    relative_error: float

    # Why this row failed, when it did. Empty on a match - the dashboard is a
    # diagnosis tool, not a scoreboard.
    rejections: list[str]


class AccuracySummary(BaseModel):
    total: int
    status_correct: int
    method_correct: int
    amount_within_2pct: int
    amount_within_10pct: int
    median_relative_error: float
    rows: list[AccuracyRow]