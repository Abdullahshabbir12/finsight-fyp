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
    rows[0].update({"Decision": "edit", "Verified Value": "900000000", "Review Note": "Corrected using source statement."})
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
    commit_review(run, rows)
    assert "revenue" not in verified_values(run)
    assert not run.metrics and not run.analysts and run.synthesis is None
