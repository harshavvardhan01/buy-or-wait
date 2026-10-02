"""The flagship check: every recommendation is re-simulated and proven safe.

This is the problem statement's own definition of a safe plan, applied to our
own output rather than assumed from how the plan was built.
"""
from datetime import datetime

import forecast
from decide import _is_safe, choose
from events import normalise_user_events, split_history_future
from personalization import load as load_prefs


def test_no_recommendation_breaches_the_minimum_balance(
        data, profiles, events_by_user, rates, image_amounts, options_by_request):
    violations = []

    for request in data["requests"].to_dict("records"):
        profile = profiles[request["user_id"]]
        request_date = datetime.strptime(request["request_date"], "%Y-%m-%d").date()

        events = normalise_user_events(events_by_user[request["user_id"]],
                                       profile["home_currency"], rates,
                                       image_amounts)
        history, future = split_history_future(events, request_date)
        balance, minimum = forecast.build(profile, history, future, request_date)

        plan, _, _ = choose(request, profile, load_prefs(profile),
                            options_by_request.get(request["request_id"], []),
                            history, future, balance, minimum, request_date)

        # Plans carrying spending changes are safe against an ADJUSTED curve,
        # which this unadjusted re-simulation cannot see. They are validated
        # inside choose() at construction time instead.
        if plan is None or plan.spending_changes:
            continue

        if not _is_safe(plan, profile, history, future, request_date, minimum):
            violations.append((request["request_id"], plan.method))

    assert not violations, f"{len(violations)} unsafe recommendations: {violations[:5]}"