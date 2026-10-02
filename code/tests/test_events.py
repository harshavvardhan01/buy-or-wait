"""Ledger normalisation: the dataset plants cancelled duplicates, refund
reversals and pending credits that must not reach the forecast."""
from datetime import date

from events import normalise_user_events, split_history_future


def _normalise(user_id, events_by_user, profiles, rates, image_amounts):
    profile = profiles[user_id]
    return normalise_user_events(events_by_user[user_id],
                                 profile["home_currency"], rates, image_amounts)


def test_user_01_drops_exactly_the_planted_noise(
        events_by_user, profiles, rates, image_amounts):
    cleaned = _normalise("user_01", events_by_user, profiles, rates, image_amounts)
    kept = {e.event_id for e in cleaned}

    # event_98 is a real charge, event_99 its settled reversal: both net out.
    assert "event_98" not in kept
    assert "event_99" not in kept
    # event_100 is a cancelled authorization; event_101 is the settled charge
    # that replaced it and must survive.
    assert "event_100" not in kept
    assert "event_101" in kept
    # event_102 is a pending debit with no link: a genuine reserved outflow.
    assert "event_102" in kept


def test_failed_events_are_dropped(events_by_user, profiles, rates, image_amounts):
    cleaned = _normalise("user_55", events_by_user, profiles, rates, image_amounts)
    kept = {e.event_id for e in cleaned}
    assert "event_5168" not in kept      # failed debit
    assert "event_5169" in kept          # its scheduled retry is real


def test_no_dropped_status_survives(events_by_user, profiles, rates, image_amounts):
    for user_id in list(events_by_user)[:20]:
        cleaned = _normalise(user_id, events_by_user, profiles, rates, image_amounts)
        for event in cleaned:
            assert event.status not in {"cancelled", "failed", "unrealized"}
            assert event.direction != "non_cash"


def test_image_amounts_fill_blanks(events_by_user, profiles, rates, image_amounts):
    cleaned = _normalise("user_55", events_by_user, profiles, rates, image_amounts)
    water_bill = next(e for e in cleaned if e.event_id == "event_5170")
    assert water_bill.amount is not None
    assert float(water_bill.amount) == 723.0


def test_split_is_exhaustive(events_by_user, profiles, rates, image_amounts):
    cleaned = _normalise("user_01", events_by_user, profiles, rates, image_amounts)
    history, future = split_history_future(cleaned, date(2024, 3, 3))
    assert len(history) + len(future) == len(cleaned)
    assert all(e.when < date(2024, 3, 3) for e in history)
    assert all(e.when >= date(2024, 3, 3) for e in future)