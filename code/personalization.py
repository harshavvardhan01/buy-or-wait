"""Parse the user's stated preferences into typed constraints."""
from dataclasses import dataclass, field


def _split(text):
    return [p.strip() for p in str(text).split("|") if p.strip()]


@dataclass
class Preferences:
    accepted_methods: list
    max_installment_months: int          # 0 means installments not considered
    protect: set
    willing_to_reduce: set
    willing_to_stop: set
    priorities: list = field(default_factory=list)

    def may_reduce(self, category):
        return category in self.willing_to_reduce and category not in self.protect

    def may_stop(self, category):
        return category in self.willing_to_stop and category not in self.protect


def load(profile):
    raw_months = str(profile["max_installment_months"]).strip()
    # Blank is meaningful, not missing: the user will not consider installments
    # at all. Defaulting it to a number would invent a preference.
    months = int(float(raw_months)) if raw_months else 0

    return Preferences(
        accepted_methods=_split(profile["payment_methods_user_will_consider"]),
        max_installment_months=months,
        protect=set(_split(profile["expense_categories_to_protect"])),
        willing_to_reduce=set(_split(
            profile["expense_categories_user_is_willing_to_reduce"])),
        willing_to_stop=set(_split(
            profile["expense_categories_user_is_willing_to_stop"])),
        priorities=_split(profile["financial_priorities"]),
    )