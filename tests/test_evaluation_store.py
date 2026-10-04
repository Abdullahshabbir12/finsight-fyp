from decimal import Decimal
import pytest
from src.database.store import load_run, list_runs, save_run
from src.demo import demo_run
from src.utils.evaluation import evaluation
from tests.test_validation import reviewed_demo


def test_accuracy_counts_and_unavailable_denominator():
    run = reviewed_demo()
    run.reviews[0].decision = "edit"
    run.reviews[0].verified_value = Decimal(500)
    run.reviews[1].decision = "unavailable"
    run.reviews[1].verified_value = None
    metrics = evaluation(run)
    assert metrics["extraction_accuracy"] == 19 / 20
    assert metrics["fields_accepted_without_changes"] == 19
    assert metrics["fields_edited_by_user"] == 1
    assert metrics["numeric_or_year_correction_count"] == 1
    assert metrics["unavailable_fields"] == 1
    assert metrics["extraction_completeness"] == 1
    assert metrics["reported_cost_subtotal"] is None


def test_no_review_accuracy_is_na():
    metrics = evaluation(demo_run())
    assert metrics["extraction_accuracy"] is None
    assert metrics["pending_review_fields"] == 21


def test_sqlite_round_trip_and_update(tmp_path):
    path = str(tmp_path / "runs.sqlite3")
    run = reviewed_demo()
    save_run(run, path)
    saved = load_run(run.id, path)
    assert saved.model_dump() == run.model_dump()
    run.company.name = "Updated synthetic name"
    save_run(run, path)
    assert len(list_runs(path)) == 1
    assert load_run(run.id, path).company.name == "Updated synthetic name"
    with pytest.raises(ValueError):
        load_run("' OR 1=1", path)


def test_field_outcomes_separate_error_types():
    from src.utils.evaluation import field_outcomes
    run = demo_run()
    run.fields[1].normalized_value = Decimal(-650000000)                     # sign fixed by reviewer
    run.fields[4].status, run.fields[4].normalized_value = "needs_review", None  # flagged but right number
    run.fields[17].raw_value, run.fields[17].normalized_value, run.fields[17].status = None, None, "missing"
    run.fields[2].normalized_value = Decimal(1)                               # wrong number
    run = reviewed_after_edits(run, {1, 2, 4, 17})
    outcomes = {row["field"]: row["outcome"] for row in field_outcomes(run)}
    assert outcomes["revenue"] == "correct"
    assert outcomes["cost_of_sales"] == "sign_corrected"
    assert outcomes["gross_profit"] == "wrong_value"
    assert outcomes["finance_cost"] == "correct_but_flagged"
    assert outcomes["operating_cash_flow"] == "filled_by_human"
    stats = evaluation(run)
    assert stats["proposal_precision"] == 18 / 20 and stats["field_recall"] == 18 / 21
    assert stats["extraction_accuracy"] == 17 / 21


def reviewed_after_edits(run, edited):
    from src.validation.review import commit_review, review_rows
    from src.demo import demo_run as fresh
    truth = {f.field_name: f.normalized_value for f in fresh().fields}
    rows = review_rows(run)
    for i, (f, row) in enumerate(zip(run.fields, rows)):
        if i in edited:
            row.update({"Decision": "edit", "Verified Value": str(truth[f.field_name]), "Entry Unit": "PKR" if f.field_name != "eps" else "PKR/share",
                        "Evidence Text": "Synthetic source", "Review Note": "Corrected."})
        else:
            row["Decision"] = "accept"
    commit_review(run, rows)
    return run


def test_aggregate_skips_demo_and_unreviewed_runs():
    from src.utils.evaluation import aggregate
    live = reviewed_demo()
    live.is_demo = False
    summaries, per_field = aggregate([live, reviewed_demo(), demo_run()])
    assert len(summaries) == 1 and summaries[0]["proposal_precision"] == 1
    assert next(r for r in per_field if r["field"] == "Revenue / Sales")["correct"] == 1
