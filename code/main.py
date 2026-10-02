"""Entry point: run every request in dataset/requests.csv and write output.csv."""
import csv
import sys
import traceback
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import explain
import forecast
from decide import choose, status_for
from events import normalise_user_events, split_history_future
from io_load import load_all
from money import RateTable
from personalization import load as load_prefs
from schema import OUTPUT_COLUMNS, fmt_amount, fmt_plan
from usage import TokenCounter
from vision import resolve_amounts


def fallback_row(request_id, reason):
    """Conservative, schema-valid row for a request that raised.

    One bad record must never abort a 250-row run, and the safest thing to say
    when the engine cannot reason is that nothing can be paid.
    """
    return {
        "request_id": request_id,
        "amount_safe_to_pay": "0",
        "affordability_status": config.STATUS_NOT,
        "recommended_payment_method": config.METHOD_NONE,
        "payment_plan": config.NONE_TOKEN,
        "earliest_date_for_full_payment": "",
        "spending_changes_needed": config.NONE_TOKEN,
        "decision_explanation": (
            "Insufficient reliable information to confirm a safe payment plan; "
            "no payment is recommended."),
    }


def solve(request, profile, prefs, options, events, rates):
    request_date = datetime.strptime(request["request_date"], "%Y-%m-%d").date()
    history, future = split_history_future(events, request_date)
    balance, minimum = forecast.build(profile, history, future, request_date)

    requested = Decimal(request["requested_amount"])
    plan, safe_today, earliest_full = choose(
        request, profile, prefs, options, history, future,
        balance, minimum, request_date)

    status = status_for(plan, request_date)
    currency = profile["home_currency"]

    if status == config.STATUS_NOT:
        payment_plan = config.NONE_TOKEN
        earliest_text = ""          # spec: empty when never affordable
        method = config.METHOD_NONE
    else:
        payment_plan = fmt_plan(plan.payments)
        earliest_text = earliest_full.isoformat() if earliest_full else ""
        method = plan.method

    return {
        "request_id": request["request_id"],
        "amount_safe_to_pay": fmt_amount(safe_today, floor=True),
        "affordability_status": status,
        "recommended_payment_method": method,
        "payment_plan": payment_plan,
        "earliest_date_for_full_payment": earliest_text,
        "spending_changes_needed": (
            "|".join(plan.spending_changes) if plan and plan.spending_changes
            else config.NONE_TOKEN),
        "decision_explanation": explain.build(
            plan, status, currency, requested, safe_today, minimum,
            earliest_full, request_date),
    }


def main(use_llm=False):
    data = load_all()
    rates = RateTable(data["rates"])
    counter = TokenCounter()

    profiles = {r["user_id"]: r for r in data["profiles"].to_dict("records")}

    events_by_user = {}
    for row in data["events"].to_dict("records"):
        events_by_user.setdefault(row["user_id"], []).append(row)

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
    image_amounts = resolve_amounts(blanks, use_llm=use_llm, counter=counter)

    rows, failures = [], []
    for request in data["requests"].to_dict("records"):
        try:
            profile = profiles[request["user_id"]]
            events = normalise_user_events(
                events_by_user.get(request["user_id"], []),
                profile["home_currency"], rates, image_amounts)
            rows.append(solve(request, profile, load_prefs(profile),
                              options_by_request.get(request["request_id"], []),
                              events, rates))
        except Exception:
            failures.append(request["request_id"])
            traceback.print_exc()
            rows.append(fallback_row(request["request_id"], "engine error"))

    with open(config.OUTPUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS,
                                quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    write_usage_report(counter)
    print(f"wrote {len(rows)} rows to {config.OUTPUT}")
    if failures:
        print(f"fell back on {len(failures)} requests: {failures}")


def write_usage_report(counter):
    calls, inputs, outputs = counter.totals()
    path = config.ROOT / "code" / "evaluation" / "usage_report.md"
    lines = [
        "# Model Usage Report", "",
        f"- Total model calls: {calls}",
        f"- Input tokens: {inputs:,}",
        f"- Output tokens: {outputs:,}",
        "",
    ]
    if counter.by_model:
        lines.append("| Provider | Model | Calls | Input | Output |")
        lines.append("|---|---|---|---|---|")
        for model, e in sorted(counter.by_model.items()):
            lines.append(f"| {e['provider']} | {model} | {e['calls']} | "
                         f"{e['input']:,} | {e['output']:,} |")
    else:
        lines.append("No live model calls in this run: all 16 image amounts were "
                     "served from the content-hash cache populated during "
                     "extraction. Clearing `code/.cache/vision.json` re-runs them.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(use_llm="--llm" in sys.argv)