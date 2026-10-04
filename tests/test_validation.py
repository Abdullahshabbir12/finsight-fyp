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


def test_profit_growth_outpacing_cash_flow_is_flagged():
    run = reviewed_demo()
    assert not any("grew materially faster" in w for w in validate_run(run))
    next(r for r in run.reviews if r.field_name == "operating_cash_flow").verified_value = Decimal(100000000)  # cash flow fell
    assert any("grew materially faster" in w for w in validate_run(run))


def test_prior_year_rows_expect_the_previous_year():
    import pytest
    run = demo_run()
    rows = review_rows(run)
    prior = next(i for i, f in enumerate(run.fields) if f.field_name == "revenue_prior_year")
    assert rows[prior]["Verified Year"] == 2024
    for row in rows:
        row["Decision"] = "accept"
    rows[prior]["Verified Year"] = 2025
    with pytest.raises(ValueError, match="2024"):
        commit_review(run, rows)


def test_saved_runs_from_before_prior_year_still_work():
    from src.calculations.ratios import calculate
    from src.catalog import FIELDS, PRIOR_FIELDS
    from src.models import Run, upgrade_run
    run = reviewed_demo()
    old = Run.model_validate_json(run.model_dump_json())
    old.fields = [f for f in old.fields if f.field_name not in PRIOR_FIELDS]
    old.reviews = [r for r in old.reviews if r.field_name not in PRIOR_FIELDS]
    upgraded = upgrade_run(old)
    assert [f.field_name for f in upgraded.fields] == list(FIELDS)
    assert all(r.decision == "unavailable" and r.note for r in upgraded.reviews if r.field_name in PRIOR_FIELDS)
    metrics = {m.name: m for m in calculate(upgraded)}
    assert metrics["revenue_growth"].value is None and metrics["current_ratio"].value is not None
