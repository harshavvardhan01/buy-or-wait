"""Detect recurring cash-flow series from a user's transaction history.

Grouping is by (category, direction): within one user a category behaves as a
single stream - rent monthly, groceries weekly. Description text varies too much
to group on ("Supermarket basket", "Neighbourhood grocer" are one series).
"""
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import config

# Income descriptions stable enough to project forward. Applied per EVENT, not
# per category: users mix a base salary with commissions and platform payouts
# under a single category, and the spec says commissions, bonuses and other
# unsettled credits do not count until they settle. Filtering rows rather than
# categories keeps the salary while dropping the gig income beside it.
PAYROLL_INCOME = re.compile(
    r"payroll|salary|wages|household income|contract payment|assignment pay"
    r"|stipend|pension|retainer", re.I)

# Variable essentials swing month to month, and the spec asks for conservative
# forecasting of them. Fixed commitments like rent and insurance are known
# exactly, so inflating those would be invention rather than caution.
VARIABLE_CATEGORIES = {
    "groceries", "dining", "transport", "shopping", "entertainment",
    "healthcare", "utilities",
}


@dataclass
class Series:
    category: str
    direction: str
    period_days: int
    amount: Decimal
    last_seen: date
    flexibility: str
    occurrences: int


def _pick_amount(amounts, rule):
    if rule == "last":
        return amounts[-1]
    if rule == "max":
        return max(amounts)
    if rule == "mean":
        return sum(amounts) / len(amounts)
    floats = sorted(float(a) for a in amounts)
    return Decimal(str(statistics.median(floats)))


def detect(history, request_date, lookback_days=None, amount_rule=None,
           sample_size=None, conservatism=None, full_payment_margin=None):
    """`full_payment_margin` is consumed by decide.choose, not used here. It is
    accepted so the calibration harness can pass one tuning dict to both."""
    lookback_days = lookback_days or config.LOOKBACK_DAYS
    amount_rule = amount_rule or config.AMOUNT_RULE
    sample_size = sample_size or config.AMOUNT_SAMPLE
    conservatism = conservatism or config.CONSERVATISM

    window_start = request_date - timedelta(days=lookback_days)
    groups = defaultdict(list)
    for event in history:
        if event.when < window_start or event.amount is None:
            continue
        if (event.direction == "credit"
                and not PAYROLL_INCOME.search(event.description)):
            continue        # gig payout, commission, bonus: not a commitment
        groups[(event.category, event.direction)].append(event)

    series = []
    for (category, direction), events in groups.items():
        # Monthly income yields only ~3 points in a 180-day window, and one
        # missed month drops it below an expense-calibrated threshold. Income
        # gets a lower bar because losing it swings the forecast far harder
        # than including it wrongly.
        floor = (config.MIN_INCOME_OCCURRENCES if direction == "credit"
                 else config.MIN_OCCURRENCES)
        if len(events) < floor:
            continue

        gaps = [(events[i + 1].when - events[i].when).days
                for i in range(len(events) - 1)]
        gaps = [g for g in gaps if g > 0]
        if not gaps:
            continue

        median_gap = statistics.median(gaps)
        period = min(config.PERIODS, key=lambda p: abs(p - median_gap))
        if abs(period - median_gap) > config.PERIOD_TOLERANCE:
            continue        # irregular: a run of one-offs, not a commitment

        recent = [e.amount for e in events[-sample_size:]]
        amount = _pick_amount(recent, amount_rule)
        if direction == "debit" and category in VARIABLE_CATEGORIES:
            amount *= Decimal(str(conservatism))

        series.append(Series(
            category=category, direction=direction, period_days=period,
            amount=amount, last_seen=events[-1].when,
            flexibility=events[-1].flexibility, occurrences=len(events),
        ))
    return series