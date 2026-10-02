"""Turn raw financial_events rows into a clean cash-event list per user."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from money import to_decimal

DROP_STATUSES = {"cancelled", "failed", "unrealized"}


def parse_date(text):
    return datetime.strptime(text, "%Y-%m-%d").date()


@dataclass
class CashEvent:
    event_id: str
    event_type: str
    description: str
    category: str
    direction: str            # debit | credit
    amount: Decimal | None # home currency; None only if unresolved
    when: date                # settlement_date if present, else event_date
    status: str
    flexibility: str
    minimum_allowed: Decimal | None

    @property
    def signed(self):
        """Cash effect: negative for money out, positive for money in."""
        if self.amount is None:
            return Decimal(0)
        return -self.amount if self.direction == "debit" else self.amount


def normalise_user_events(rows, home_currency, rate_table, image_amounts=None):
    """rows: list of dicts for ONE user. Returns cleaned list of CashEvent.

    `image_amounts` maps event_id -> Decimal for the 16 blank-amount events.
    It is a parameter rather than a global so the OCR stage can be skipped
    entirely in tests without touching this module.
    """
    image_amounts = image_amounts or {}
    by_id = {r["event_id"]: r for r in rows}

    # Pass 1: decide which event_ids to discard. Collected first because a
    # refund reversal has to remove an event that appears EARLIER in the list.
    discard = set()
    for row in rows:
        eid, status = row["event_id"], row["status"]
        linked = row["linked_event_id"]

        if status in DROP_STATUSES or row["direction"] == "non_cash":
            discard.add(eid)
            continue

        if row["event_type"] == "refund":
            if status == "pending":
                discard.add(eid)          # unsettled credit: never counted
            elif status == "settled" and linked in by_id:
                discard.add(eid)          # reversal nets out...
                discard.add(linked)       # ...along with the original debit
            continue

        # A pending debit that points at an earlier event is a duplicate or
        # re-authorization of it, not a second real outflow.
        if status == "pending" and row["direction"] == "debit" and linked in by_id:
            discard.add(eid)

    # Pass 2: build the surviving events.
    cleaned = []
    for row in rows:
        if row["event_id"] in discard:
            continue

        amount = to_decimal(row["amount"])
        if amount is None:
            amount = image_amounts.get(row["event_id"])   # may still be None

        when = parse_date(row["settlement_date"] or row["event_date"])

        if amount is not None and row["currency"] != home_currency:
            amount = rate_table.convert(amount, row["currency"],
                                        home_currency, when.isoformat())

        cleaned.append(CashEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            description=row["description"],
            category=row["category"],
            direction=row["direction"],
            amount=amount,
            when=when,
            status=row["status"],
            flexibility=row["flexibility"],
            minimum_allowed=to_decimal(row["minimum_allowed_amount"]),
        ))

    cleaned.sort(key=lambda ev: (ev.when, ev.event_id))
    return cleaned


def split_history_future(events, request_date):
    """History drives recurrence detection; future events are confirmed cash."""
    history = [e for e in events if e.when < request_date]
    future = [e for e in events if e.when >= request_date]
    return history, future