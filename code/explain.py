"""Deterministic explanation templates.

Every number here comes from the engine. No LLM touches these strings, so an
explanation can never disagree with the plan it describes.
"""
import config


def _money(currency, amount):
    return f"{currency} {float(amount):,.2f}".rstrip("0").rstrip(".")


def build(plan, status, currency, requested, safe_today, minimum,
          earliest_full, request_date):
    if status == config.STATUS_NOT:
        if safe_today > 0:
            return (f"Only {_money(currency, safe_today)} of the "
                    f"{_money(currency, requested)} can be paid without dropping "
                    f"below the {_money(currency, minimum)} minimum balance, and "
                    f"the full amount is not reachable within the forecast period.")
        return (f"Committed expenses keep the balance at or below the "
                f"{_money(currency, minimum)} minimum, so no part of the "
                f"{_money(currency, requested)} can be paid safely.")

    if plan.method == "full_payment":
        return (f"Pay {_money(currency, requested)} today. The balance stays "
                f"above the {_money(currency, minimum)} minimum for the whole "
                f"90-day forecast.")

    if plan.method == "wait":
        return (f"Waiting until {earliest_full} allows the full "
                f"{_money(currency, requested)} to be paid while keeping the "
                f"{_money(currency, minimum)} minimum balance intact.")

    if plan.method == "partial_payment":
        first = plan.payments[0][1]
        second = plan.payments[1][1]
        return (f"Pay {_money(currency, first)} today and the remaining "
                f"{_money(currency, second)} on {plan.payments[1][0]}, which "
                f"keeps the balance above {_money(currency, minimum)} throughout.")

    count = len(plan.payments)
    each = plan.payments[0][1]
    return (f"Spread the cost over {count} payments of {_money(currency, each)} "
            f"starting {plan.start_date}, totalling "
            f"{_money(currency, plan.total_paid)}. Each payment clears while "
            f"holding the {_money(currency, minimum)} minimum balance.")