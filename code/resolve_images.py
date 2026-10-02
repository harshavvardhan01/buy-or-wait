"""One-off: resolve all blank amounts and print them for eyeball verification."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from io_load import load_all
from usage import TokenCounter
from vision import resolve_amounts


def main(use_llm=True, refresh=False, only=None):
    data = load_all()
    events, images = data["events"], data["images"]
    link = dict(zip(images["related_event_id"], images["image_id"], strict=True))

    blanks = [
        {"event_id": r["event_id"], "image_id": link[r["event_id"]],
         "description": r["description"], "category": r["category"],
         "direction": r["direction"], "currency": r["currency"],
         "event_date": r["event_date"]}
        for _, r in events.iterrows()
        if r["amount"] == "" and r["event_id"] in link
    ]

    counter = TokenCounter()
    if only:
        blanks = [b for b in blanks if b["image_id"] in only]
    resolved = resolve_amounts(blanks, use_llm=use_llm,
                               counter=counter, refresh=refresh)

    print(f"{'image':10} {'event':13} {'currency':4}  amount        description")
    cache = json.loads((config.CACHE / "vision.json").read_text())
    by_image = {v["image_id"]: v for v in cache.values()}
    for b in blanks:
        amount = resolved.get(b["event_id"], "UNRESOLVED")
        meta = by_image.get(b["image_id"], {})
        print(f"{b['image_id']:10} {b['event_id']:13} {b['currency']:4}  "
              f"{amount!s:13} {meta.get('source','-'):7} {b['description']}")


if __name__ == "__main__":
    args = sys.argv[1:]
    only = {a for a in args if a.startswith("image_")} or None
    main(use_llm="--no-llm" not in args,
         refresh="--refresh" in args,
         only=only)