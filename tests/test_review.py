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



def test_every_problem_is_reported_at_once():
    from src.validation.review import ReviewError
    run = demo_run()
    rows = review_rows(run)  # all pending
    rows[0].update({"Decision": "accept"})
    with pytest.raises(ReviewError) as exc:
        commit_review(run, rows)
    assert len(exc.value.problems) == len(rows) - 1
    assert not run.reviews


def test_reasons_replace_typed_notes():
    from src.validation.review import accept_ready, mark_remaining_unavailable
    run = demo_run()
    rows = review_rows(run)
    rows[0].update({"Decision": "edit", "Verified Value": "900", "Reason": "Wrong number"})  # evidence prefilled
    rows[1].update({"Decision": "unavailable", "Reason": "Not reported as a single line"})
    assert accept_ready(run, rows) == len(rows) - 2
    assert mark_remaining_unavailable(rows, "Not reported in this document") == 0
    commit_review(run, rows)
    assert run.reviews[0].reason == "Wrong number" and run.reviews[1].explanation() == "Not reported as a single line"
    assert run.reviews[2].reason == ""


def test_edit_needs_evidence_and_reason_or_note():
    from src.validation.review import ReviewError
    run = demo_run()
    rows = accepted_rows(run)
    rows[0].update({"Decision": "edit", "Verified Value": "900", "Evidence Text": "", "Reason": "Wrong number"})
    rows[1].update({"Decision": "edit", "Verified Value": "640"})  # evidence prefilled, but no reason or note
    rows[2].update({"Decision": "unavailable", "Reason": "Other (explain in note)"})
    with pytest.raises(ReviewError) as exc:
        commit_review(run, rows)
    assert len(exc.value.problems) == 3


def test_draft_survives_and_is_cleared_on_finish():
    from src.validation.review import save_draft
    run = demo_run()
    rows = review_rows(run)
    rows[0].update({"Decision": "edit", "Verified Value": "900", "Reason": "Wrong number", "Review Note": float("nan")})
    save_draft(run, rows)
    reopened = review_rows(run)
    assert reopened[0]["Decision"] == "edit" and reopened[0]["Verified Value"] == "900" and reopened[0]["Review Note"] == ""
    for row in reopened[1:]:
        row["Decision"] = "accept"
    commit_review(run, reopened)
    assert run.review_draft == [] and verified_values(run)["revenue"] == Decimal("900000000")
