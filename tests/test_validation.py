from decimal import Decimal
from src.demo import demo_run
from src.validation.accounting import reconcile, validate_run
from src.validation.review import commit_review, review_rows


def reviewed_demo():
    run = demo_run()
    rows = review_rows(run)
    for row in rows:
        row["Decision"] = "accept"
    commit_review(run, rows)
    return run


def test_tolerance():
    assert reconcile(Decimal(100), Decimal(101))[0]
    assert not reconcile(Decimal(100), Decimal(105))[0]
    assert reconcile(Decimal(0), Decimal(0))[0]


def test_reconciliations_and_warnings_do_not_change_values():
    run = reviewed_demo()
    assert not validate_run(run)
    run.reviews[0].verified_value = Decimal(500000000)
    run.reviews[8].verified_value = Decimal(100000000)
    original = run.model_dump_json()
    warnings = validate_run(run)
    assert any("Assets versus" in w for w in warnings)
    assert any("Gross profit versus" in w for w in warnings)
    assert run.model_dump_json() == original


def test_negative_and_missing_warnings():
    run = reviewed_demo()
    run.reviews[16].verified_value = Decimal(-1)
    run.reviews[0].decision = "unavailable"
    run.reviews[0].verified_value = None
    warnings = validate_run(run)
    assert any("Missing key" in w for w in warnings)
    assert any("Equity is nonpositive" in w for w in warnings)
