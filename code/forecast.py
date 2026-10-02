"""90-day daily balance projection. The single source of every output number.

Call chain:
    calibrate.py / main.py
        -> events.normalise_user_events()   clean the raw ledger
        -> events.split_history_future()    history drives patterns, future is fact
        -> forecast.build()                 <- THIS MODULE: daily balance array
        -> forecast.safe_today()            amount_safe_to_pay
        -> forecast.earliest_full_payment() earliest_date_for_full_payment
"""
import re
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import config
import recurrence

# Descriptions that mark the END of an income stream. Matched against the most
# recent income occurrence only: an older "previous employer" row followed by a
# newer "new employer payroll" row means income continued.
#
# Which income rows are eligible to project at all is decided in recurrence.py,
# per event. This module only decides whether the stream has stopped outright.
INCOME_TERMINAL = re.compile(
    r"final employer|previous employer|final settlement|last payroll", re.I)


def income_has_stopped(history, future):
    """True when the latest income evidence says the stream ended.

    `latest` is picked by date across BOTH history and future, because a
    confirmed future salary is the strongest possible evidence income continues.
    """
    incomes = [e for e in list(history) + list(future)
               if e.direction == "credit" and e.event_type == "income"]
    if not incomes:
        return True
    latest = max(incomes, key=lambda e: e.when)
    return bool(INCOME_TERMINAL.search(latest.description))


def _next_monthly(anchor, after):
    """Next occurrence on the same day-of-month strictly after `after`.

    Stepping by a fixed 30 days makes a rent payment drift backwards ~1 day per
    month, which over a 90-day window can add or drop a whole payment. Calendar
    stepping keeps the day-of-month stable and clamps for short months, so the
    31st becomes the 28th in February rather than spilling into March.
    """
    year, month, day = anchor.year, anchor.month, anchor.day
    while True:
        month += 1
        if month > 12:
            month, year = 1, year + 1
        candidate = date(year, month, min(day, monthrange(year, month)[1]))
        if candidate > after:
            return candidate


def _occurrences(series, request_date, horizon):
    """Yield every projected date for a series inside the forecast window."""
    if series.period_days >= 28:
        current = _next_monthly(series.last_seen, request_date - timedelta(days=1))
        while (current - request_date).days <= horizon:
            yield current
            current = _next_monthly(current, current)
    else:
        current = series.last_seen + timedelta(days=series.period_days)
        while current < request_date:
            current += timedelta(days=series.period_days)
        while (current - request_date).days <= horizon:
            yield current
            current += timedelta(days=series.period_days)


def build(profile, history, future, request_date, horizon=None,adjustments=None, **tuning):
    """Project the daily balance.

    Returns (balance_by_day, minimum_balance). balance_by_day[0] is the balance
    on request_date; index d is d days later. `tuning` is forwarded to
    recurrence.detect so the calibration harness can sweep parameters without
    this function knowing what they are.
    """
    horizon = horizon or config.HORIZON_DAYS
    flows = defaultdict(Decimal)

    # 1. Confirmed future events land exactly where the ledger says.
    #    `seen_dates` is keyed by category so a projected series can tell
    #    whether a real event already occupies that slot.
    seen_dates = defaultdict(list)
    for event in future:
        offset = (event.when - request_date).days
        if 0 <= offset <= horizon and event.amount is not None:
            flows[offset] += event.signed
            seen_dates[event.category].append(event.when)

    # 2. Project recurring series. Eligible income rows were already filtered
    #    in recurrence.detect; here we only drop income that has ended.
    stopped = income_has_stopped(history, future)
    adjustments = adjustments or {}
    for series in recurrence.detect(history, request_date, **tuning):
        if series.direction == "credit" and stopped:
            continue

        amount = series.amount
        if series.category in adjustments:
            replacement = adjustments[series.category]
            if replacement is None:
                continue                 # stopped entirely
            amount = replacement

        sign = 1 if series.direction == "credit" else -1
        for when in _occurrences(series, request_date, horizon):
            clash = any(abs((d - when).days) <= config.DEDUPE_WINDOW
                        for d in seen_dates.get(series.category, ()))
            if clash:
                continue
            flows[(when - request_date).days] += sign * amount

    balance = [Decimal(profile["current_available_balance"])]
    for day in range(1, horizon + 1):
        balance.append(balance[-1] + flows[day])

    return balance, Decimal(profile["minimum_balance_to_keep"])


def headroom(balance, minimum):
    """Most that can leave the account today without ever breaching the floor."""
    return min(balance) - minimum


def safe_today(balance, minimum, requested):
    return max(Decimal(0), min(headroom(balance, minimum), requested))


def earliest_full_payment(balance, minimum, requested, request_date):
    """First day d where paying `requested` keeps every later day above floor.

    Uses a suffix minimum because a payment on day d only depresses days >= d,
    which turns what looks like an O(n^2) scan into a single backward pass.
    """
    horizon = len(balance) - 1
    suffix_min = [Decimal(0)] * (horizon + 1)
    running = balance[horizon]
    for day in range(horizon, -1, -1):
        running = min(running, balance[day])
        suffix_min[day] = running

    for day in range(horizon + 1):
        if suffix_min[day] - requested >= minimum:
            return request_date + timedelta(days=day)
    return None