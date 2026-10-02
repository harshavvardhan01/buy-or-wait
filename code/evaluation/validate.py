"""Invariant checks that run against output.csv. Stage 7 expands this."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from schema import OUTPUT_COLUMNS


def validate():
    out = pd.read_csv(config.OUTPUT, dtype=str, keep_default_na=False)
    req = pd.read_csv(config.DATASET / "requests.csv", dtype=str, keep_default_na=False)
    failures = []

    if tuple(out.columns) != OUTPUT_COLUMNS:
        failures.append(f"column mismatch: {tuple(out.columns)}")
    if len(out) != len(req):
        failures.append(f"row count {len(out)} != {len(req)}")
    if set(out["request_id"]) != set(req["request_id"]):
        failures.append("request_id set mismatch")
    if not out["request_id"].is_unique:
        failures.append("duplicate request_id")

    bad = out[~out["affordability_status"].isin(config.ALL_STATUSES)]
    if len(bad):
        failures.append(f"{len(bad)} invalid affordability_status")
    bad = out[~out["recommended_payment_method"].isin(config.ALL_METHODS)]
    if len(bad):
        failures.append(f"{len(bad)} invalid recommended_payment_method")

    merged = out.merge(req[["request_id", "requested_amount"]], on="request_id")
    for _, r in merged.iterrows():
        amt, cap = float(r["amount_safe_to_pay"]), float(r["requested_amount"])
        if not (0 <= amt <= cap):
            failures.append(f"{r['request_id']}: {amt} outside [0, {cap}]")
            break

    for f in failures:
        print("FAIL:", f)
    if not failures:
        print(f"ALL CHECKS PASS ({len(out)} rows)")
    return not failures


if __name__ == "__main__":
    sys.exit(0 if validate() else 1)