"""Adapter between the wire format and the engine.

The engine consumes plain string dicts because it was built against CSV rows.
Rather than rewrite it, this module converts Pydantic models into that shape -
one place to change if the engine's inputs are ever typed properly.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

import config
import forecast
import recurrence
from decide import LAST_REJECTIONS, choose, status_for
from events import normalise_user_events, split_history_future
from explain import build as build_explanation
from money import RateTable
from personalization import load as load_prefs

from .models import (
    AnalyzeRequest,
    AnalyzeResponse,
    DecisionOut,
    EventIn,
    PaymentOut,
    ProjectionOut,
    ProjectionPoint,
    ReasoningOut,
    SeriesOut,
)

MONEY = Decimal("0.01")


def _money(value: Decimal, floor: bool = False) -> Decimal:
    """Quantize at the serialization boundary, never inside the engine.

    The engine keeps full precision so repeated additions across 90 days do not
    accumulate rounding error; only what leaves the process is rounded. `floor`
    is for amount_safe_to_pay - never advise spending a cent we cannot prove is
    safe.
    """
    return value.quantize(MONEY, rounding=ROUND_FLOOR if floor else ROUND_HALF_UP)

def _pipe(values: list[str]) -> str:
    """The engine parses preference lists from pipe-delimited strings."""
    return "|".join(values)


def _profile_dict(profile) -> dict[str, str]:
    return {
        "user_id": profile.user_id,
        "home_currency": profile.home_currency,
        "current_available_balance": str(profile.current_available_balance),
        "minimum_balance_to_keep": str(profile.minimum_balance_to_keep),
        "financial_priorities": _pipe(profile.financial_priorities),
        "expense_categories_to_protect": _pipe(profile.expense_categories_to_protect),
        "expense_categories_user_is_willing_to_reduce":
            _pipe(profile.expense_categories_user_is_willing_to_reduce),
        "expense_categories_user_is_willing_to_stop":
            _pipe(profile.expense_categories_user_is_willing_to_stop),
        "payment_methods_user_will_consider":
            _pipe(profile.payment_methods_user_will_consider),
        "max_installment_months": ("" if profile.max_installment_months is None
                                   else str(profile.max_installment_months)),
    }


def _event_dict(event: EventIn) -> dict[str, str]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "description": event.description,
        "category": event.category,
        "direction": event.direction,
        "amount": "" if event.amount is None else str(event.amount),
        "currency": event.currency,
        "event_date": event.event_date.isoformat(),
        "settlement_date": (event.settlement_date.isoformat()
                            if event.settlement_date else ""),
        "status": event.status,
        "flexibility": event.flexibility,
        "minimum_allowed_amount": ("" if event.minimum_allowed_amount is None
                                   else str(event.minimum_allowed_amount)),
        "linked_event_id": event.linked_event_id,
    }


def _option_dict(option) -> dict[str, str]:
    return {
        "payment_option_id": option.payment_option_id,
        "payment_method": option.payment_method,
        "payment_amount": str(option.payment_amount),
        "number_of_payments": str(option.number_of_payments),
        "first_payment_date": (option.first_payment_date.isoformat()
                               if option.first_payment_date else ""),
        "payment_frequency_days": ("" if option.payment_frequency_days is None
                                   else str(option.payment_frequency_days)),
        "financing_fee": str(option.financing_fee),
        "total_payable_amount": ("" if option.total_payable_amount is None
                                 else str(option.total_payable_amount)),
    }


def _request_dict(request) -> dict[str, str]:
    return {
        "request_id": request.request_id,
        "request_date": request.request_date.isoformat(),
        "request_type": request.request_type,
        "requested_amount": str(request.requested_amount),
        "desired_completion_date": (request.desired_completion_date.isoformat()
                                    if request.desired_completion_date else ""),
        "allows_partial_payment": str(request.allows_partial_payment).lower(),
        "request_text": request.request_text,
    }


def analyze(payload: AnalyzeRequest,
            rates: RateTable,
            image_amounts: dict[str, Decimal] | None = None) -> AnalyzeResponse:
    profile = _profile_dict(payload.profile)
    request = _request_dict(payload.request)
    request_date = payload.request.request_date

    events = normalise_user_events(
        [_event_dict(e) for e in payload.events],
        payload.profile.home_currency, rates, image_amounts or {})
    history, future = split_history_future(events, request_date)

    balance, minimum = forecast.build(profile, history, future, request_date)
    requested = payload.request.requested_amount

    plan, safe_today, earliest_full = choose(
        request, profile, load_prefs(profile),
        [_option_dict(o) for o in payload.payment_options],
        history, future, balance, minimum, request_date)

    # LAST_REJECTIONS is module-level state that choose() clears on entry, so it
    # is copied here before anything else can call choose and overwrite it.
    rejections = list(LAST_REJECTIONS)

    status = status_for(plan, request_date)
    explanation = build_explanation(plan, status, payload.profile.home_currency,
                                    requested, safe_today, minimum,
                                    earliest_full, request_date)

    decision = DecisionOut(
        amount_safe_to_pay=_money(safe_today, floor=True),
        affordability_status=status,
        recommended_payment_method=(plan.method if plan else config.METHOD_NONE),
        payment_plan=([PaymentOut(date=d, amount=_money(a))
                       for d, a in plan.payments] if plan else []),
        earliest_date_for_full_payment=(
            None if status == config.STATUS_NOT else earliest_full),
        spending_changes_needed=(plan.spending_changes if plan else []),
        decision_explanation=explanation,
    )

    # `trough_index` must be computed before the downsample: weekly resolution
    # deliberately keeps the trough, so it needs to know where it is first.
    trough_index = min(range(len(balance)), key=lambda i: balance[i])

    # Weekly keeps the trough and both endpoints, so the chart's shape and its
    # critical point survive downsampling. A naive every-7th-day slice would
    # frequently drop the single most important day on the curve.
    step = 7 if payload.resolution == "weekly" else 1
    keep = sorted({0, trough_index, len(balance) - 1}
                  | set(range(0, len(balance), step)))

    projection = ProjectionOut(
        points=[ProjectionPoint(date=request_date + timedelta(days=i),
                                balance=_money(balance[i])) for i in keep],
        minimum_balance=_money(minimum),
        trough_date=request_date + timedelta(days=trough_index),
        trough_balance=_money(balance[trough_index]),
        headroom=_money(forecast.headroom(balance, minimum)),
    )

    series = recurrence.detect(history, request_date)
    reasoning = ReasoningOut(
        detected_series=[
            SeriesOut(
                category=s.category, direction=s.direction,
                period_days=s.period_days, amount=_money(s.amount),
                monthly_equivalent=_money(
                    s.amount * Decimal(30) / Decimal(s.period_days)),
                last_seen=s.last_seen, flexibility=s.flexibility,
                occurrences=s.occurrences)
            for s in series],
        confirmed_future_events=[
            e for e in payload.events
            if (e.settlement_date or e.event_date) >= request_date],
        rejected_plans=rejections,
        income_projected=not forecast.income_has_stopped(history, future),
    )

    return AnalyzeResponse(decision=decision, projection=projection,
                           reasoning=reasoning)