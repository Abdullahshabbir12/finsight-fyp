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
