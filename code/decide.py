"""Enumerate candidate payment plans, filter to safe ones, rank by the spec."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

import config
import forecast
import recurrence

# Populated on every choose() call and cleared at its start. Diagnostics only -
# nothing in the pipeline reads it, so it can never affect output. It exists
# because "no candidate survived" is otherwise indistinguishable from "no
# candidate was ever built".
LAST_REJECTIONS: list[str] = []


def _reject(reason):
    LAST_REJECTIONS.append(reason)


@dataclass
class Plan:
    method: str
    payments: list                       # [(date, Decimal)] chronological
    total_paid: Decimal
    spending_changes: list = field(default_factory=list)
    option_id: str = ""

    @property
    def start_date(self):
        return self.payments[0][0]

    @property
    def last_date(self):
        return self.payments[-1][0]

    def completes_by(self, deadline):
        return deadline is None or self.last_date <= deadline


def _parse_date(text):
    return datetime.strptime(text, "%Y-%m-%d").date() if text else None


def _is_safe(plan, profile, history, future, request_date, minimum, tuning=None):
    """Re-simulate the plan and assert the floor is never breached.

    This is the spec's own definition of safety, run as a check on our own
    output rather than trusted as a side effect of how the plan was built.

    `tuning` must match what the caller used to build its own balance curve,
    otherwise headroom and safety are computed against different forecasts and
    a plan can be rejected for breaching a curve nobody else ever saw.
    """
    balance, _ = forecast.build(profile, history, future, request_date,
                                **(tuning or {}))
    running = list(balance)

    for when, amount in plan.payments:
        offset = (when - request_date).days
        if offset > config.HORIZON_DAYS:
            continue          # beyond the forecast: nothing to check against
        for day in range(max(offset, 0), len(running)):
            running[day] -= amount

    return min(running) >= minimum


def _change_options(history, request_date, prefs, tuning=None):
    """Flexible series the user has authorised changing, best saving first.

    Each option carries the event_id of the most recent occurrence in that
    category, because the output format identifies a change by event rather
    than by category.
    """
    options = []
    for series in recurrence.detect(history, request_date, **(tuning or {})):
        if series.direction != "debit" or series.flexibility == "fixed":
            continue

        latest = max((e for e in history if e.category == series.category),
                     key=lambda e: e.when, default=None)
        if latest is None:
            continue

        period = Decimal(series.period_days)
        monthly = series.amount * Decimal(30) / period

        if prefs.may_stop(series.category) and "stoppable" in series.flexibility:
            options.append((monthly, series.category, None,
                            f"stop:{latest.event_id}"))
        elif prefs.may_reduce(series.category) and "reducible" in series.flexibility:
            floor = latest.minimum_allowed or Decimal(0)
            if floor < series.amount:
                saving = (series.amount - floor) * Decimal(30) / period
                options.append((saving, series.category, floor,
                                f"reduce_to:{latest.event_id}:{floor}"))

    options.sort(key=lambda option: -option[0])
    return options[:config.MAX_SPENDING_CHANGES]


def choose(request, profile, prefs, options, history, future,
           balance, minimum, request_date, tuning=None):
    """Return (Plan | None, safe_today, earliest_full)."""
    LAST_REJECTIONS.clear()

    requested = Decimal(request["requested_amount"])
    deadline = _parse_date(request["desired_completion_date"])
    allows_partial = str(request["allows_partial_payment"]).lower() == "true"

    safe_today = forecast.safe_today(balance, minimum, requested)
    earliest_full = forecast.earliest_full_payment(
        balance, minimum, requested, request_date)

    # Declaring "affordable today" is a knife-edge test: a 1-2% forecast
    # over-prediction flips a case that genuinely needs a plan. The margin
    # demands real slack before calling it safe, rather than tightening the
    # forecast itself, which no parameter reliably does.
    margin = Decimal(str((tuning or {}).get(
        "full_payment_margin", config.FULL_PAYMENT_MARGIN)))

    candidates = []

    # --- full payment today ---
    if "full_payment" not in prefs.accepted_methods:
        _reject("full_payment not in accepted methods")
    elif safe_today < requested * margin:
        _reject(f"full_payment: safe_today {float(safe_today):,.2f} < "
                f"requested {float(requested):,.2f} x{float(margin)}")
    else:
        candidates.append(Plan("full_payment", [(request_date, requested)],
                               requested))

    # --- installments, built only from the options actually offered ---
    if ("installments" not in prefs.accepted_methods
            or not prefs.max_installment_months):
        _reject(f"installments not considered (accepted={prefs.accepted_methods}, "
                f"max_months={prefs.max_installment_months})")
    else:
        for opt in options:
            if opt["payment_method"] != "installments":
                continue

            option_id = opt["payment_option_id"]
            count = int(float(opt["number_of_payments"]))
            if count > prefs.max_installment_months:
                _reject(f"{option_id}: {count} payments > "
                        f"max {prefs.max_installment_months}")
                continue

            first = _parse_date(opt["first_payment_date"])
            step = int(float(opt["payment_frequency_days"] or 30))
            amount = Decimal(opt["payment_amount"])
            payments = [(first + timedelta(days=step * i), amount)
                        for i in range(count)]
            total = Decimal(opt["total_payable_amount"] or amount * count)
            plan = Plan("installments", payments, total, option_id=option_id)

            if not plan.completes_by(deadline):
                _reject(f"{option_id}: ends {plan.last_date} after "
                        f"deadline {deadline}")
                continue
            if not _is_safe(plan, profile, history, future, request_date,
                            minimum, tuning):
                _reject(f"{option_id}: unsafe (total {float(total):,.0f}, "
                        f"headroom {float(forecast.headroom(balance, minimum)):,.0f})")
                continue
            candidates.append(plan)

    # --- partial payment: pay what is safe now, the rest when it becomes safe ---
    if "partial_payment" not in prefs.accepted_methods:
        _reject("partial_payment not in accepted methods")
    elif not allows_partial:
        _reject("partial_payment: request does not allow it")
    elif not Decimal(0) < safe_today < requested:
        _reject(f"partial_payment: safe_today {float(safe_today):,.2f} "
                f"not strictly between 0 and requested")
    elif not earliest_full:
        _reject("partial_payment: no earliest_full date for the remainder")
    elif deadline is not None and earliest_full > deadline:
        _reject(f"partial_payment: remainder date {earliest_full} "
                f"after deadline {deadline}")
    else:
        remainder = requested - safe_today
        candidates.append(Plan("partial_payment",
                               [(request_date, safe_today),
                                (earliest_full, remainder)], requested))

    # --- wait for the whole amount ---
    if "full_payment" in prefs.accepted_methods:
        if not earliest_full:
            _reject("wait: full amount never safe inside the forecast")
        elif earliest_full > request_date:
            if deadline is not None and earliest_full > deadline:
                _reject(f"wait: earliest {earliest_full} after deadline {deadline}")
            else:
                candidates.append(Plan("wait", [(earliest_full, requested)],
                                       requested))

    # --- second pass: allow authorised spending changes ---
    if not candidates:
        changes = _change_options(history, request_date, prefs, tuning)
        if not changes:
            _reject("no authorised flexible spending to change")
        else:
            adjustments = {cat: repl for _, cat, repl, _ in changes}
            labels = [label for _, _, _, label in changes]
            adjusted, _ = forecast.build(profile, history, future, request_date,
                                         adjustments=adjustments,
                                         **(tuning or {}))
            adj_safe = forecast.safe_today(adjusted, minimum, requested)
            adj_earliest = forecast.earliest_full_payment(
                adjusted, minimum, requested, request_date)

            if "full_payment" in prefs.accepted_methods and adj_safe >= requested:
                candidates.append(Plan("full_payment",
                                       [(request_date, requested)], requested,
                                       spending_changes=labels))
            elif ("full_payment" in prefs.accepted_methods and adj_earliest
                  and adj_earliest > request_date
                  and (deadline is None or adj_earliest <= deadline)):
                candidates.append(Plan("wait", [(adj_earliest, requested)],
                                       requested, spending_changes=labels))
            else:
                _reject(f"even with changes: safe {float(adj_safe):,.2f}, "
                        f"earliest {adj_earliest}")

    if not candidates:
        return None, safe_today, earliest_full

    # Spec ranking, ascending after inverting the booleans: completes by the
    # deadline, then no spending changes, then least paid, earliest start,
    # fewest payments, then option id for a deterministic tie-break.
    candidates.sort(key=lambda p: (
        not p.completes_by(deadline),
        bool(p.spending_changes),
        p.total_paid,
        p.start_date,
        len(p.payments),
        p.option_id,
    ))
    return candidates[0], safe_today, earliest_full


def status_for(plan, request_date):
    if plan is None:
        return config.STATUS_NOT
    if plan.method == "wait":
        return config.STATUS_LATER
    if (plan.method == "full_payment" and not plan.spending_changes
            and plan.start_date == request_date):
        return config.STATUS_NOW
    return config.STATUS_PLAN