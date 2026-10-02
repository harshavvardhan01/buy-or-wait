"""Grid-search forecast parameters against the 25 solved samples.

Status accuracy is what scores, so the grid ranks on it. Amount error is kept
as a tie-break because a 2% exact-match threshold is too tight for the search
to climb on its own.
"""
import itertools
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import forecast
from decide import choose, status_for
from events import normalise_user_events, split_history_future
from io_load import load_all
from money import RateTable
from personalization import load as load_prefs
from vision import resolve_amounts

TOLERANCE = Decimal("0.02")
CLOSE = Decimal("0.10")


def load_context():
    data = load_all()
    rates = RateTable(data["rates"])
    profiles = {row["user_id"]: row for row in data["profiles"].to_dict("records")}

    by_user = {}
    for row in data["events"].to_dict("records"):
        by_user.setdefault(row["user_id"], []).append(row)

    options_by_request = {}
    for row in data["options"].to_dict("records"):
        options_by_request.setdefault(row["request_id"], []).append(row)

        link = dict(zip(data["images"]["related_event_id"],
                    data["images"]["image_id"], strict=True))
    blanks = [{"event_id": r["event_id"], "image_id": link[r["event_id"]],
               "description": r["description"], "category": r["category"],
               "direction": r["direction"], "currency": r["currency"],
               "event_date": r["event_date"]}
              for r in data["events"].to_dict("records")
              if r["amount"] == "" and r["event_id"] in link]
    image_amounts = resolve_amounts(blanks, use_llm=False)

    return data, rates, profiles, by_user, image_amounts, options_by_request


def evaluate(samples, rates, profiles, by_user, image_amounts,
             options_by_request, tuning=None):
    """Returns (rows, status_hits, method_hits, mismatches).

    `tuning` is a plain dict rather than **kwargs so it can be forwarded intact
    to both forecast.build and choose, keeping the safety re-check and the
    headroom calculation on the same forecast.
    """
    tuning = tuning or {}
    rows, status_hits, method_hits, mismatches = [], 0, 0, []

    for sample in samples:
        user_id = sample["user_id"]
        request_date = datetime.strptime(sample["request_date"], "%Y-%m-%d").date()
        profile = profiles[user_id]

        events = normalise_user_events(by_user[user_id], profile["home_currency"],
                                       rates, image_amounts)
        history, future = split_history_future(events, request_date)
        balance, minimum = forecast.build(profile, history, future,
                                          request_date, **tuning)

        requested = Decimal(sample["requested_amount"])
        predicted = forecast.safe_today(balance, minimum, requested)
        actual = Decimal(sample["amount_safe_to_pay"])
        error = abs(predicted - actual) / max(actual, Decimal(1))
        rows.append((sample["request_id"], actual, predicted, error))

        plan, safe, earliest = choose(
            sample, profile, load_prefs(profile),
            options_by_request.get(sample["request_id"], []),
            history, future, balance, minimum, request_date, tuning=tuning)

        got_status = status_for(plan, request_date)
        got_method = plan.method if plan else config.METHOD_NONE

        if got_status == sample["affordability_status"]:
            status_hits += 1
        else:
            mismatches.append((sample["request_id"], got_status,
                               sample["affordability_status"], got_method,
                               sample["recommended_payment_method"],
                               safe, actual, earliest))
        if got_method == sample["recommended_payment_method"]:
            method_hits += 1

    return rows, status_hits, method_hits, mismatches


def summarise(rows):
    errors = sorted(e for _, _, _, e in rows)
    return {
        "exact": sum(1 for e in errors if e < TOLERANCE),
        "close": sum(1 for e in errors if e < CLOSE),
        "zeros": sum(1 for _, _, p, _ in rows if p == 0),
        "median_err": errors[len(errors) // 2],
    }


def main():
    context = load_context()
    data = context[0]
    args = context[1:]
    samples = data["samples"].to_dict("records")

    grid = {
        "lookback_days": [150, 180, 240, 365],
        "amount_rule": ["median", "mean", "max", "last"],
        "sample_size": [3, 4, 6],
        "conservatism": [1.0, 1.05, 1.10],
    }
    keys = list(grid)
    best = None

    for combo in itertools.product(*(grid[k] for k in keys)):
        tuning = dict(zip(keys, combo, strict=True))
        rows, status_hits, method_hits, _ = evaluate(samples, *args, tuning=tuning)
        stats = summarise(rows)

        score = (status_hits, stats["close"], -stats["median_err"])
        if best is None or score > best[0]:
            best = (score, tuning)
            print(f"  new best  status={status_hits:2}/25  method={method_hits:2}/25  "
                  f"within10%={stats['close']:2}/25  exact={stats['exact']:2}/25  "
                  f"zeros={stats['zeros']}  {tuning}")

    tuning = best[1]
    rows, status_hits, method_hits, mismatches = evaluate(
        samples, *args, tuning=tuning)
    stats = summarise(rows)

    print(f"\nBEST {tuning}")
    print(f"  status={status_hits}/25   method={method_hits}/25")
    print(f"  exact(<2%)={stats['exact']}/25   within10%={stats['close']}/25   "
          f"zeros={stats['zeros']}   median_err={float(stats['median_err']):.1%}\n")

    for request_id, actual, predicted, error in rows:
        mark = "OK " if error < TOLERANCE else ("~  " if error < CLOSE else "   ")
        print(f"{mark}{request_id:12} actual={float(actual):>16,.2f} "
              f"pred={float(predicted):>16,.2f} err={float(error):>8.1%}")

    over = sum(1 for _, actual, predicted, _ in rows if predicted > actual)
    print(f"\nover-predicting: {over}/25   under: {len(rows) - over}/25")

    print("\nSTATUS MISMATCHES")
    for rid, got_s, want_s, got_m, want_m, safe, actual, earliest in mismatches:
        print(f"  {rid:12} got {got_s:22} want {want_s:22} | "
              f"method {got_m:16} want {want_m:16} | "
              f"safe={float(safe):,.2f} want={float(actual):,.2f} "
              f"earliest={earliest}")


if __name__ == "__main__":
    main()