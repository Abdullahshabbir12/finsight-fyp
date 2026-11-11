"""Finding cards: structured checks, earnings-quality indicators and analyst decisions with history."""
from decimal import Decimal
import pytest
from src.validation.accounting import current_decision, decide, findings, validate_run
from tests.test_bank import bank_run
from tests.test_validation import reviewed_demo


def set_value(run, key, value):
    next(r for r in run.reviews if r.field_name == key).verified_value = Decimal(value)


def by_key(run):
    return {f.key: f for f in findings(run)}


def test_clean_runs_have_no_findings_and_text_matches_validate_run():
    assert findings(reviewed_demo()) == [] and findings(bank_run()) == []
    run = reviewed_demo()
    set_value(run, "total_assets", 100000000)
    assert [f.detail for f in findings(run)] == validate_run(run)        # same messages as before, one per card


def test_cards_carry_figures_arithmetic_and_next_steps():
    run = reviewed_demo()
    set_value(run, "total_assets", 100000000)
    card = by_key(run)["balance_sheet_identity"]
    assert card.priority == "high" and card.category == "Data check"
    assert card.fields == ["total_assets", "total_liabilities", "equity"]
    assert "PKR 100.00 m - (PKR 650.00 m + PKR 850.00 m)" in card.calculation
    assert card.why and len(card.next_steps) >= 2


def test_accruals_and_cash_conversion():
    run = reviewed_demo()                                                   # profit 105 m, cash flow 130 m: no flag
    assert "profit_above_cash_flow" not in by_key(run)
    set_value(run, "operating_cash_flow", -200000000)                      # (105 + 200) / 1,450 = 21% accruals
    cards = by_key(run)
    assert cards["high_accruals"].priority == "medium" and "21.0%" in cards["high_accruals"].detail
    assert cards["profit_above_cash_flow"].priority == "medium"           # negative cash flow makes it more serious
    set_value(run, "operating_cash_flow", 100000000)                       # small gap: low priority, no accruals card
    cards = by_key(run)
    assert cards["profit_above_cash_flow"].priority == "low" and "high_accruals" not in cards


def test_receivables_growing_faster_than_revenue():
    run = reviewed_demo()                                                   # receivables +7.1%, revenue +11.1%
    assert "receivables_outpacing_revenue" not in by_key(run)
    set_value(run, "trade_receivables", 200000000)                         # +42.9% vs +11.1%
    card = by_key(run)["receivables_outpacing_revenue"]
    assert "42.9%" in card.detail and "11.1%" in card.detail and "from 57 to 73" in card.detail


def test_bank_provision_reversal_is_an_earnings_quality_finding():
    run = bank_run(provisions=-50, profit_before_tax=300, tax_expense=180)  # reversal adds 50 to 250 before tax
    card = by_key(run)["provision_reversal"]
    assert card.category == "Earnings quality" and "16.7%" in card.detail
    assert "provision_reversal" not in by_key(bank_run())                  # a normal charge


def test_analyst_decisions_keep_history_and_notice_changes():
    run = reviewed_demo()
    set_value(run, "total_assets", 100000000)
    card = by_key(run)["balance_sheet_identity"]
    with pytest.raises(ValueError, match="Explain why"):
        decide(run, card, "dismissed", "  ", "2026-11-11T10:00")
    decide(run, card, "investigating", "", "2026-11-11T10:00")
    decide(run, card, "dismissed", "Assets typed wrong; corrected", "2026-11-11T10:05")
    latest, changed = current_decision(run, card)
    assert latest.status == "dismissed" and not changed and len(run.finding_decisions[card.key]) == 2
    set_value(run, "total_assets", 200000000)                              # the figures change after the decision
    assert current_decision(run, by_key(run)["balance_sheet_identity"])[1]
    from src.models import Run
    assert Run.model_validate_json(run.model_dump_json()).finding_decisions == run.finding_decisions


def test_findings_never_change_values():
    run = reviewed_demo()
    set_value(run, "operating_cash_flow", -200000000)
    before = run.model_dump_json()
    findings(run)
    assert run.model_dump_json() == before
