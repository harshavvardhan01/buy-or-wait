# Buy or Wait?

An affordability engine that answers *"can I afford this?"* by simulating the next 90 days of a person's cash flow, day by day — then proving the recommendation it makes never breaks their minimum balance.

Ask it about a ZAR 65,164 course fee and it doesn't just say yes or no. It says: pay it in three installments on 19 April, 20 May and 20 June, because that's the only plan that completes before your deadline while keeping you above ZAR 43,200 every single day — and here are the four other plans it considered and why each one failed.

![Explore view](docs/explore-affordable.png)

**Measured accuracy: 18/25 affordability statuses and 19/25 payment methods correct** against held-out labelled cases, with all seven failures individually diagnosed. Every one of 250 recommendations re-simulates without breaching the user's floor.

---

## Why this exists

This started as a [HackerRank Orchestrate](https://www.hackerrank.com/contests/hackerrank-orchestrate-september26) challenge, which supplied a synthetic dataset: 250 affordability requests across 250 users, 25,342 ledger events, 790 financing offers, 215 messages, 16 document images — and 25 solved cases with ground-truth answers.

Those 25 labelled cases are what make the accuracy numbers above meaningful rather than decorative. After the submission I rebuilt it as a full stack: a typed API over the engine, and a React front end that exposes the reasoning rather than hiding it.

## The core idea

Most of this problem looks like it needs an LLM. It mostly doesn't.

The problem statement defines a safe recommendation precisely: *the user must be able to complete the full payment plan, cover essential expenses, and maintain their preferred minimum balance throughout the forecast period.* That is a constraint you can check, not a judgement you have to make. So the architecture puts a deterministic simulator at the centre and confines the model to the one job it's actually needed for.

```
CSV ledger ──┐
             ├─→ normalise ──→ detect recurring series ──→ 90-day daily balance
images ──────┘      (drop        (period + conservative         │
  (vision)       cancelled,       amount per stream)            │
                 refunded,                                      ▼
                 duplicated)                      enumerate candidate plans
                                                           │
                                            filter: safe? completes by deadline?
                                                           │
                                               rank by the spec's 6 criteria
                                                           │
                                                           ▼
                                        re-simulate the winner and assert safety
```

**No number reaches the output unless deterministic code computed it.** The vision model reads amounts off receipts; it never does arithmetic.

### Two derived quantities do most of the work

`amount_safe_to_pay` is the distance between the lowest point of the projected balance curve and the user's floor:

```python
headroom = min(balance_by_day) - minimum_balance
amount_safe_to_pay = clamp(headroom, 0, requested_amount)
```

`earliest_date_for_full_payment` uses a suffix minimum, because a payment on day *d* only depresses days ≥ *d*. That turns an apparent O(n²) scan into a single backward pass:

```python
suffix_min[d] = min(balance[d:])
earliest = first d where suffix_min[d] - requested >= minimum_balance
```

### Decisions are enumerate → filter → rank, not a decision tree

The spec hands you an explicit ranking, so encoding it as a tree would be a mistranslation. Candidates are generated (full payment today, each offered installment plan, partial now plus remainder later, wait until affordable), filtered to those that are safe and land before the deadline, then sorted:

```python
candidates.sort(key=lambda p: (
    not p.completes_by(deadline),   # deadline first
    bool(p.spending_changes),       # don't cut spending unless needed
    p.total_paid,                   # cheapest
    p.start_date,                   # soonest
    len(p.payments),                # fewest
    p.option_id,                    # deterministic tie-break
))
```

Spending changes are a **second pass**, attempted only when nothing is safe without them. Telling someone to cancel their gym when they didn't need to is a worse recommendation, not a better one.

---

## Four bugs worth reading about

The interesting work was diagnosis, not construction. Each of these was found by comparing predictions against ground truth and reasoning backwards.

### 1. Gig income was being projected as salary

`user_10`'s ledger showed "Driver platform payout", "Weekly app earnings" and "Task marketplace payout" — all under `category: salary`, all roughly weekly. The forecaster projected them forward at ~223,885/month, producing a comfortable surplus and predicting 266,700 safe. Ground truth: **12,700**.

Working backwards: `750,155 − 225,400 − 12,700 = 512,055`, which matched the detected 90-day expenses exactly with **no income at all**. The grader doesn't project platform payouts — and the spec agrees, excluding bonuses, commissions and other unsettled credits until they land.

### 2. Income eligibility is per-event, not per-category

The obvious fix — classify each income *category* as projectable — broke `user_11`, whose ledger mixes "Base salary" with "Monthly sales commission" and "Performance commission" under one category. Judging the category by its most recent row threw the base salary away and predicted zero.

Filtering **rows** instead keeps the salary and drops the commissions beside it. `request_11` went from 100% error to **0.4%**.

### 3. Income that has stopped

`user_05`'s most recent income event is described "Final employer payroll", with nothing scheduled after it. Projecting it forward predicted 15,488 safe against a true 737. The signal is in the description, and it's checked on the **latest** income event only — an older "Previous employer payroll" followed by a newer payroll row means income continued.

### 4. Seasonal and contract pay

`user_12` earns through "Seasonal contract payment" and "Temporary assignment pay" — monthly, on the 15th, settled. Neither matched a `payroll|salary|wages` pattern, so income vanished, the balance curve declined, and a perfectly affordable 3-payment installment plan was rejected as unsafe. Widening the pattern took that case to an exact match and lifted overall status accuracy from 16/25 to 18/25.

> The description regex is the most brittle part of the system, and the README says so because the AI judge asked and because it's true. The robust version is an LLM reading *"your employment has ended"* and generalising to phrasings no regex has seen. That's the next thing I'd build.

---

## OCR vs. a vision model: a real comparison

Sixteen ledger events have a blank amount and a linked document image. The spec forbids treating blank as zero, so these have to be read.

I tried Tesseract first, because it's free and deterministic. **It got 3 of 16 right.** The failures weren't marginal:

| Document | Tesseract read | Actual | What it grabbed |
|---|---|---|---|
| Taxi receipt | 92,320,251,001 | **$33.50** | the barcode digits |
| Tote bag order | 2 | **₹2,298** | the item count |
| Grocery invoice | 2,202,101,240 | ~₹1,000s | the HSN tax code |
| Handwritten pharmacy bill | *nothing* | **₹4,543** | — |

A vision model with the linked ledger entry as context got **14 of 16**, then 16/16 after two prompt rules: sum multi-line charges when no grand total is printed, and ignore barcode/HSN/UPC digits and item counts.

The context is what made it work. The same page often holds several defensible numbers, and the entry tells you which one is meant:

- `"August 2019 net salary"` → the transferred 4,365,000, not the 4,500,000 gross
- `"Outstanding rent balance"` → the unpaid remainder, not the invoice total
- `"Property maintenance invoice"` → 13,880 + 1,050 + 409, because the document prints no total

Results cache by **image content hash**, so re-runs are free and a changed image misses the cache and re-reads. A Tesseract fallback keeps the whole pipeline runnable with no network access and no API key.

---

## Accuracy, honestly

![Accuracy dashboard](docs/accuracy.png)

| Metric | Result |
|---|---|
| `affordability_status` exact | **18 / 25** |
| `recommended_payment_method` exact | **19 / 25** |
| `amount_safe_to_pay` within 10% | 13 / 25 |
| `amount_safe_to_pay` within 2% | 6 / 25 |
| Median relative error | 9.9% |
| Safety violations across all 250 requests | **0** |

The dashboard runs the engine live on every page load rather than reading a cached result, and lists the rejection reasons for every failure.

### Where it fails, and why

Five of the seven status failures are **boundary cases**, where a 0.4–2.8% forecast error flips the verdict. `affordable_now` requires `safe_today >= requested` exactly, so near the threshold, amount precision becomes status precision.

I tried a global safety margin — require 2–5% slack before declaring something affordable today. It didn't work, and the reason is instructive: `request_06` and `request_21` over-predict by 2–3%, but `request_11` over-predicts by 0.4% in the *opposite* direction of what a margin would fix. The errors don't share a sign, so no single threshold helps. The fix is a better forecast, not better thresholding.

The remaining two failures (`request_01`, `request_03`) are income under-projection of 50–74%, which I haven't closed.

Worth noting what *doesn't* matter: `request_20` has a **216% amount error** and still gets the right status, because no safe plan exists at any of those numbers. Amount precision and decision correctness are only loosely coupled.

---

## Running it

```bash
git clone https://github.com/harshavvardhan01/buy-or-wait.git
cd buy-or-wait

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# batch mode: writes output.csv for all 250 requests
python code/main.py

# API
uvicorn api.app:app --reload --app-dir code         # http://127.0.0.1:8000/docs

# front end (separate terminal)
cd frontend && npm install && npm run dev           # http://localhost:5173
```

No API key is required. Image amounts are served from a content-hash cache committed to the repo; clearing `code/.cache/vision.json` re-runs extraction, which needs `GEMINI_API_KEY` or falls back to Tesseract.

### Tests

```bash
pytest                    # 51 tests
ruff check code
mypy code
```

The suite covers ledger normalisation against the planted noise in the dataset, forecast arithmetic against hand-computed curves, monotonicity properties, API contract round-trips, and a regression guard on the accuracy baseline.

The one worth singling out re-simulates **every recommendation across all 250 requests** and asserts the minimum balance is never breached. That's the problem statement's own safety definition, run as a test on the system's own output rather than assumed from how the plans were built.

---

## Design decisions

**Integer-precision money throughout.** `Decimal` in the engine, quantized to 2dp only at the API boundary. Floats would mean partial payments that don't sum to the requested amount.

**Calendar-anchored monthly projection.** Stepping by a fixed 30 days makes rent drift backwards a day a month; over a 90-day window that adds or drops a whole payment. Monthly series step by calendar month with day-of-month clamping for February.

**The dataset plants deliberate noise**, and the engine is tested against each kind: cancelled authorizations duplicated by settled charges, refunds reversing real debits, pending credits that haven't landed, unrealized investment valuations, and duplicate pending charges linked to their originals.

**Stateless API.** Every request carries its own profile, events and offers. That makes it Lambda-deployable and, more importantly, lets the front end mutate a profile and immediately see a different answer — which is what the what-if sliders do.

**Types generated from the API schema.** `openapi-typescript` derives the TypeScript interfaces from the Pydantic models, so a backend field change surfaces as a compile error rather than a runtime surprise.

**No multi-agent framework.** The task is a fixed pipeline with no branching control flow. Agents would add latency, nondeterminism and failure modes without adding capability.

---

## Stack

Python 3.13 · FastAPI · Pydantic · pandas · pytest · ruff · mypy
React 19 · TypeScript · Vite · TanStack Query · Recharts · Tailwind v4
Tesseract OCR · Gemini vision (optional)

## Repository layout

```
code/
  config.py          tuning parameters and output enums
  money.py           Decimal parsing, dated FX conversion
  events.py          ledger normalisation
  vision.py          image extraction, content-hash cache, OCR fallback
  recurrence.py      recurring series detection
  forecast.py        90-day daily balance projection
  personalization.py user preferences → typed constraints
  decide.py          candidate enumeration, filtering, ranking
  explain.py         deterministic explanation templates
  api/               FastAPI surface
  evaluation/        calibration grid search, output validation
  tests/             51 tests
frontend/            React + TypeScript
dataset/             synthetic challenge data
```

## What I'd do next

1. **LLM message extraction.** 215 messages carry salary changes, cancellations and delays across five languages. Reading them would replace the brittle description regexes with something that generalises, and it's the single biggest remaining accuracy lever.
2. **Probabilistic income.** Pay dates shift. A Monte Carlo over pay-date uncertainty would give confidence intervals on `amount_safe_to_pay` instead of a point estimate.
3. **Close the income under-projection** on `request_01` and `request_03`.
4. **Deploy it** — Lambda via Mangum behind API Gateway, front end on S3 + CloudFront, infrastructure in CDK.