"""Dump everything the engine knows about one request. Use when calibrating."""
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import forecast
import recurrence
from decide import LAST_REJECTIONS, choose, status_for
from events import normalise_user_events, split_history_future
from io_load import load_all
from money import RateTable
from personalization import load as load_prefs
from vision import resolve_amounts


def main(request_id):
    data = load_all()
    source = (data["samples"] if request_id in set(data["samples"]["request_id"])
              else data["requests"])
    row = source[source["request_id"] == request_id].iloc[0].to_dict()

    profile = data["profiles"].set_index("user_id").loc[row["user_id"]].to_dict()
    profile["user_id"] = row["user_id"]
    request_date = datetime.strptime(row["request_date"], "%Y-%m-%d").date()

    raw = data["events"][data["events"]["user_id"] == row["user_id"]].to_dict("records")
    link = dict(zip(data["images"]["related_event_id"],
                data["images"]["image_id"], strict=True))
    blanks = [{"event_id": r["event_id"], "image_id": link[r["event_id"]],
               "description": r["description"], "category": r["category"],
               "direction": r["direction"], "currency": r["currency"],
               "event_date": r["event_date"]}
              for r in raw if r["amount"] == "" and r["event_id"] in link]

    events = normalise_user_events(raw, profile["home_currency"],
                                   RateTable(data["rates"]),
                                   resolve_amounts(blanks, use_llm=False))
    history, future = split_history_future(events, request_date)
    balance, minimum = forecast.build(profile, history, future, request_date)

    requested = Decimal(row["requested_amount"])
    print(f"{request_id}  {row['user_id']}  {row['request_type']}  "
          f"{profile['home_currency']}")
    print(f"  balance={float(profile['current_available_balance']):,.2f}  "
          f"min={float(minimum):,.2f}  requested={float(requested):,.2f}")
    print(f"  request_date={request_date}  desired={row['desired_completion_date']}  "
          f"allows_partial={row['allows_partial_payment']}")

    print("\n  detected series:")
    for s in sorted(recurrence.detect(history, request_date),
                    key=lambda x: -float(x.amount) * 30 / x.period_days):
        monthly = float(s.amount) * 30 / s.period_days
        print(f"    {s.category:22} {s.direction:6} per={s.period_days:2}d  "
              f"amt={float(s.amount):>14,.2f}  ~/mo={monthly:>14,.2f}  "
              f"n={s.occurrences} last={s.last_seen} flex={s.flexibility}")

    print("\n  confirmed future events:")
    for e in future:
        if (e.when - request_date).days <= config.HORIZON_DAYS:
            print(f"    {e.when}  {e.direction:6} {float(e.amount or 0):>14,.2f}  "
                  f"{e.category:18} [{e.status}] {e.description}")

    trough = min(range(len(balance)), key=lambda d: balance[d])
    print(f"\n  balance floor {float(min(balance)):,.2f} on day {trough} "
          f"({request_date + timedelta(days=trough)})")
    print(f"  headroom={float(forecast.headroom(balance, minimum)):,.2f}")
    print(f"  safe_today={float(forecast.safe_today(balance, minimum, requested)):,.2f}")
    print(f"  earliest_full="
          f"{forecast.earliest_full_payment(balance, minimum, requested, request_date)}")

    options = data["options"]
    opts = options[options["request_id"] == request_id].to_dict("records")
    prefs = load_prefs(profile)
    plan, _safe, _earliest = choose(row, profile, prefs, opts, history, future,
                                    balance, minimum, request_date)

    print(f"\n  prefs: methods={prefs.accepted_methods} "
          f"max_months={prefs.max_installment_months}")
    print(f"  chosen: {plan.method if plan else 'NONE'} "
          f"-> {status_for(plan, request_date)}")
    if plan:
        print(f"  plan: {[(str(d), float(a)) for d, a in plan.payments]}")
        print(f"  changes: {plan.spending_changes or 'none'}")
    print("  rejections:")
    for reason in LAST_REJECTIONS:
        print(f"    {reason}")

    if "amount_safe_to_pay" in row:
        print(f"\n  GROUND TRUTH safe={float(Decimal(row['amount_safe_to_pay'])):,.2f} "
              f"status={row['affordability_status']} "
              f"method={row['recommended_payment_method']} "
              f"plan={row['payment_plan']}")


if __name__ == "__main__":
    main(sys.argv[1])