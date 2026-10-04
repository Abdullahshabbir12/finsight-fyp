from decimal import Decimal
import pytest
from src.demo import demo_run
from src.validation.review import commit_review, review_rows, verified_values


def accepted_rows(run):
    rows = review_rows(run)
    for row in rows:
        row["Decision"] = "accept"
    return rows


def test_pending_is_blocked_and_atomic():
    run = demo_run()
    with pytest.raises(ValueError):
        verified_values(run)
    with pytest.raises(ValueError):
        commit_review(run, review_rows(run))
    assert not run.reviews
    assert run.verified_at is None


def test_original_and_correction_are_preserved():
    run = demo_run()
    rows = accepted_rows(run)
    # The demo statement unit is PKR million, so 900 means PKR 900,000,000.
    assert rows[0]["Entry Unit"] == "PKR million" and rows[0]["Verified Value"] == "1000"
    rows[0].update({"Decision": "edit", "Verified Value": "900", "Review Note": "Corrected using source statement."})
    commit_review(run, rows)
    assert verified_values(run)["revenue"] == Decimal("900000000")
    assert run.fields[0].normalized_value == Decimal("1000000000")
    assert run.fields[0].raw_value == "1000"
    assert run.verified_at


def test_accept_cannot_hide_changed_value():
    run = demo_run()
    rows = accepted_rows(run)
    rows[0]["Verified Value"] = "42"
    with pytest.raises(ValueError, match="edit decision"):
        commit_review(run, rows)


def test_unavailable_never_enters_engine_and_revision_clears_outputs():
    run = demo_run()
    rows = accepted_rows(run)
    rows[0]["Decision"] = "unavailable"
    rows[0]["Review Note"] = "Not reported as a single line."
    commit_review(run, rows)
    assert "revenue" not in verified_values(run)
    assert not run.metrics and not run.analysts and run.synthesis is None


def test_unavailable_requires_a_reason():
    run = demo_run()
    rows = accepted_rows(run)
    rows[0]["Decision"] = "unavailable"
    with pytest.raises(ValueError, match="why the value is unavailable"):
        commit_review(run, rows)


def test_entry_unit_scales_and_is_restricted():
    run = demo_run()
    rows = accepted_rows(run)
    rows[0].update({"Decision": "edit", "Verified Value": "900,000,000", "Entry Unit": "PKR", "Review Note": "Base units."})
    commit_review(run, rows)
    assert verified_values(run)["revenue"] == Decimal("900000000")
    rows = accepted_rows(demo_run())
    rows[19].update({"Entry Unit": "PKR million"})  # EPS can never use a statement scale
    with pytest.raises(ValueError, match="Entry Unit"):
        commit_review(demo_run(), rows)


def test_saved_review_reopens_in_base_units():
    run = demo_run()
    commit_review(run, accepted_rows(run))
    row = review_rows(run)[0]
    assert row["Entry Unit"] == "PKR" and row["Verified Value"] == "1000000000"
