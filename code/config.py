"""Central configuration. No logic, no magic numbers scattered elsewhere."""
from pathlib import Path

# repo root = two levels up from this file (code/config.py -> code/ -> root)
ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "dataset"
IMAGES = DATASET / "media" / "images"
OUTPUT = ROOT / "output.csv"
CACHE = ROOT / "code" / ".cache"

# Spec: "Forecast the user's balance for the next 90 days"
HORIZON_DAYS = 90

# --- forecast tuning (calibrated against sample_requests.csv) ---
LOOKBACK_DAYS = 150          # history window for recurrence detection
MIN_OCCURRENCES = 3          # below this an expense stream is not a pattern
MIN_INCOME_OCCURRENCES = 2   # monthly payroll gives few points; see recurrence.py
PERIODS = (7, 14, 30, 60)    # weekly / fortnightly / monthly / bimonthly
PERIOD_TOLERANCE = 4         # median gap must land within this many days
AMOUNT_RULE = "median"       # median | mean | max | last
AMOUNT_SAMPLE = 3            # how many recent occurrences feed the estimate
CONSERVATISM = 1.0           # multiplier on projected variable essential spending
DEDUPE_WINDOW = 3            # days within which a projection duplicates a real event
MAX_SPENDING_CHANGES = 3     # spec caps the spending_changes_needed list

# Allowed enum values, copied verbatim from problem_statement.md
STATUS_NOW = "affordable_now"
STATUS_PLAN = "affordable_with_plan"
STATUS_LATER = "affordable_later"
STATUS_NOT = "not_affordable"
ALL_STATUSES = (STATUS_NOW, STATUS_PLAN, STATUS_LATER, STATUS_NOT)

METHOD_FULL = "full_payment"
METHOD_PARTIAL = "partial_payment"
METHOD_INSTALLMENTS = "installments"
METHOD_WAIT = "wait"
METHOD_NONE = "not_recommended"
ALL_METHODS = (METHOD_FULL, METHOD_PARTIAL, METHOD_INSTALLMENTS,
               METHOD_WAIT, METHOD_NONE)

NONE_TOKEN = "none"
FULL_PAYMENT_MARGIN = 1.0