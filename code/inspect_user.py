"""Manual check that normalisation drops exactly the right rows."""
import sys
from datetime import datetime
from pathlib import Path

from vision import resolve_amounts

sys.path.insert(0, str(Path(__file__).resolve().parent))

from events import normalise_user_events, split_history_future
from io_load import load_all
from money import RateTable


def main(user_id, request_date_text):
    data = load_all()
    rate_table = RateTable(data["rates"])
    home = data["profiles"].set_index("user_id").loc[user_id, "home_currency"]

    raw = data["events"][data["events"]["user_id"] == user_id].to_dict("records")
    link = dict(zip(data["images"]["related_event_id"],
                    data["images"]["image_id"], strict=True))
    blanks = [
        {"event_id": r["event_id"], "image_id": link[r["event_id"]],
         "description": r["description"], "category": r["category"],
         "direction": r["direction"], "currency": r["currency"],
         "event_date": r["event_date"]}
        for r in raw if r["amount"] == "" and r["event_id"] in link
    ]
    image_amounts = resolve_amounts(blanks, use_llm=False) if blanks else {}

    cleaned = normalise_user_events(raw, home, rate_table, image_amounts)

    kept = {e.event_id for e in cleaned}
    dropped = sorted({r["event_id"] for r in raw} - kept,
                     key=lambda x: int(x.split("_")[1]))

    request_date = datetime.strptime(request_date_text, "%Y-%m-%d").date()
    history, future = split_history_future(cleaned, request_date)

    print(f"{user_id} home={home}  raw={len(raw)} kept={len(cleaned)} dropped={len(dropped)}")
    print("dropped:", ", ".join(dropped))
    print(f"history={len(history)} future={len(future)}")
    for e in future:
        print(f"  FUTURE {e.event_id} {e.when} {e.direction:6} {e.amount} "
              f"{e.category} [{e.status}] {e.description}")
    missing = [e.event_id for e in cleaned if e.amount is None]
    print("unresolved amounts:", missing or "none")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])