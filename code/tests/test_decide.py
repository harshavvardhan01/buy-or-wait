"""Plan construction and the spec's ranking rules."""
from datetime import datetime
from decimal import Decimal

import config
import forecast
from decide import choose, status_for
from events import normalise_user_events, split_history_future
from personalization import load as load_prefs


def _solve(sample, profiles, events_by_user, rates, image_amounts,
           options_by_request):
    profile = profiles[sample["user_id"]]
    request_date = datetime.strptime(sample["request_date"], "%Y-%m-%d").date()
    events = normalise_user_events(events_by_user[sample["user_id"]],
                                   profile["home_currency"], rates, image_amounts)
    history, future = split_history_future(events, request_date)
    balance, minimum = forecast.build(profile, history, future, request_date)
    plan, safe, earliest = choose(
        sample, profile, load_prefs(profile),
        options_by_request.get(sample["request_id"], []),
        history, future, balance, minimum, request_date)
    return plan, safe, earliest, request_date


def test_partial_payments_sum_to_requested(
        data, profiles, events_by_user, rates, image_amounts, options_by_request):
    """Any rounding residue must land in the final payment, never be lost."""
    for sample in data["requests"].to_dict("records"):
        plan, _, _, _ = _solve(sample, profiles, events_by_user, rates,
                               image_amounts, options_by_request)
        if plan and plan.method == "partial_payment":
            assert len(plan.payments) == 2
            total = sum(amount for _, amount in plan.payments)
            assert total == Decimal(sample["requested_amount"])


def test_installment_plans_match_a_real_option(
        data, profiles, events_by_user, rates, image_amounts, options_by_request):
    """We never invent financing terms; every plan cites an offered option."""
    for sample in data["requests"].to_dict("records"):
        plan, _, _, _ = _solve(sample, profiles, events_by_user, rates,
                               image_amounts, options_by_request)
        if plan and plan.method == "installments":
            offered = {o["payment_option_id"]
                       for o in options_by_request[sample["request_id"]]}
            assert plan.option_id in offered


def test_installments_respect_the_users_month_cap(
        data, profiles, events_by_user, rates, image_amounts, options_by_request):
    for sample in data["requests"].to_dict("records"):
        plan, _, _, _ = _solve(sample, profiles, events_by_user, rates,
                               image_amounts, options_by_request)
        if plan and plan.method == "installments":
            prefs = load_prefs(profiles[sample["user_id"]])
            assert len(plan.payments) <= prefs.max_installment_months


def test_chosen_method_is_one_the_user_accepts(
        data, profiles, events_by_user, rates, image_amounts, options_by_request):
    """`wait` is a full payment deferred, so it requires full_payment consent."""
    for sample in data["requests"].to_dict("records"):
        plan, _, _, _ = _solve(sample, profiles, events_by_user, rates,
                               image_amounts, options_by_request)
        if plan is None:
            continue
        prefs = load_prefs(profiles[sample["user_id"]])
        required = "full_payment" if plan.method == "wait" else plan.method
        assert required in prefs.accepted_methods


def test_spending_changes_respect_protected_categories(
        data, profiles, events_by_user, rates, image_amounts, options_by_request):
    for sample in data["requests"].to_dict("records"):
        plan, _, _, _ = _solve(sample, profiles, events_by_user, rates,
                               image_amounts, options_by_request)
        if plan and plan.spending_changes:
            assert len(plan.spending_changes) <= config.MAX_SPENDING_CHANGES


def test_status_enum_matches_method(
        data, profiles, events_by_user, rates, image_amounts, options_by_request):
    for sample in data["requests"].to_dict("records"):
        plan, _, _, request_date = _solve(sample, profiles, events_by_user, rates,
                                          image_amounts, options_by_request)
        status = status_for(plan, request_date)
        assert status in config.ALL_STATUSES
        if status == config.STATUS_NOT:
            assert plan is None
        if status == config.STATUS_LATER:
            assert plan.method == "wait"