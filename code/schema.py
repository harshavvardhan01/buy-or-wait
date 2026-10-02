"""The output contract. Single source of truth for column names and order."""
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

OUTPUT_COLUMNS = (
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
)


def fmt_amount(value, floor=False):
    """Format money for CSV output.

    `floor` is True for amount_safe_to_pay: never advise spending a cent we
    cannot prove is safe. Everything else rounds half-up as normal.
    """
    d = Decimal(str(value))
    rule = ROUND_FLOOR if floor else ROUND_HALF_UP
    q = d.quantize(Decimal("0.01"), rounding=rule)
    # drop a trailing ".00" so output matches the sample style (25256, not 25256.00)
    return str(q.normalize()) if q == q.to_integral_value() else str(q)


def fmt_plan(payments):
    """payments: list of (date_str, amount). Returns 'YYYY-MM-DD:amt|...' or 'none'."""
    if not payments:
        return "none"
    return "|".join(f"{d}:{fmt_amount(a)}" for d, a in payments)