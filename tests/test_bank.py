"""Bank support: catalogue, ratios, checks, units, page selection and AI rules, on a synthetic bank."""
from datetime import datetime, timezone
from decimal import Decimal
import pymupdf
import pytest
from src.catalog import BANK_FIELDS, FIELDS, LABELS, catalog
from src.models import Company, FinancialField, Page, Run
from src.validation.review import commit_review, review_rows, verified_values

VALUES = {  # base PKR unless noted; chosen so every identity holds exactly
    "interest_earned": 1000, "interest_expensed": 600, "net_interest_income": 400, "non_interest_income": 100,
    "total_income": 500, "operating_expenses": 250, "profit_before_provisions": 250, "provisions": 50,
    "profit_before_tax": 200, "tax_expense": 80, "net_profit": 120, "eps": 6, "total_assets": 10000,
    "cash_and_treasury": 500, "lendings": 300, "investments": 4000, "advances_net": 4700, "total_liabilities": 9200,
    "deposits": 8000, "borrowings": 900, "equity": 800, "gross_advances": 5000, "non_performing_loans": 400,
    "npl_provisions": 300, "casa_deposits": 6000, "capital_adequacy_ratio": Decimal("18.25"), "number_of_shares": 20,
    "net_interest_income_prior_year": 350, "net_profit_prior_year": 100, "total_assets_prior_year": 9000,
    "advances_net_prior_year": 4200, "deposits_prior_year": 7200, "equity_prior_year": 700,
}
UNIT = {"eps": "PKR/share", "number_of_shares": "shares", "capital_adequacy_ratio": "percent"}


def bank_run(**changes) -> Run:
    values = {**VALUES, **changes}
    fields = []
    for key in catalog("bank"):
        year = 2023 if key.endswith("_prior_year") else 2024
        raw = str(values[key])
        fields.append(FinancialField(field_name=key, reporting_year=year, raw_value=raw, normalized_value=Decimal(raw),
                                     unit=UNIT.get(key, "PKR"), source_page=1, source_text=f"{LABELS[key]} {raw}",
                                     confidence=.9, status="extracted"))
    run = Run(id="bank-test", company=Company(name="Synthetic Bank", industry="Banking", financial_year=2024, sector="bank"),
              pages=[Page(number=1, text="synthetic")], fields=fields, created_at=datetime.now(timezone.utc).isoformat())
    rows = review_rows(run)
    for row in rows:
        row["Decision"] = "accept"
    commit_review(run, rows)
    return run


def test_bank_catalogue_shares_common_fields():
    assert len(BANK_FIELDS) == 33 and len(FIELDS) == 27
    assert {"total_assets", "equity", "net_profit", "eps"} <= set(BANK_FIELDS) & set(FIELDS)
    assert "revenue" not in BANK_FIELDS and "deposits" not in FIELDS
    assert set(verified_values(bank_run())) == set(BANK_FIELDS)


def test_bank_ratios():
    from src.calculations.ratios import calculate
    m = {x.name: x.value for x in calculate(bank_run())}
    assert m["net_interest_margin"] == Decimal(400) / 9000          # earning assets = lendings + investments + advances
    assert m["cost_to_income"] == Decimal("0.5") and m["advances_to_deposits"] == Decimal("0.5875")
    assert m["infection_ratio"] == Decimal("0.08") and m["coverage_ratio"] == Decimal("0.75")
    assert m["casa_ratio"] == Decimal("0.75") and m["equity_to_assets"] == Decimal("0.08")
    assert m["capital_adequacy"] == Decimal("0.1825")                # reported, not recalculated
    assert m["deposits_growth"] == Decimal(800) / 7200 and m["return_on_average_equity"] == Decimal(120) / 750
    assert "current_ratio" not in m and "gross_profit_margin" not in m


def test_bank_ratio_edge_cases():
    from src.calculations.ratios import calculate
    m = {x.name: x for x in calculate(bank_run(non_performing_loans=0, lendings=0, investments=0, advances_net=0))}
    assert m["coverage_ratio"].value is None and m["coverage_ratio"].reason      # no NPLs: coverage is not meaningful
    assert m["net_interest_margin"].value is None                              # no earning assets
    assert "[Lendings to Financial Institutions] + [Investments]" in m["net_interest_margin"].formula


def test_bank_checks_pass_when_consistent_and_flag_problems():
    from src.validation.accounting import validate_run
    assert validate_run(bank_run()) == []
    broken = validate_run(bank_run(net_interest_income=450, capital_adequacy_ratio=Decimal("9.5"), non_performing_loans=900))
    assert any("Net interest income versus" in w for w in broken)
    assert any("capital adequacy is below 11.5%" in w for w in broken)
    assert any("exceed 10% of gross advances" in w for w in broken)
    assert any("outside 0-100%" in w for w in validate_run(bank_run(capital_adequacy_ratio=Decimal("1825"))))
    assert not any("current assets" in w.lower() for w in broken)            # company checks do not apply to banks


def test_capital_adequacy_is_read_as_a_percentage():
    from src.extraction.service import canonical_unit, normalize
    assert canonical_unit("%", "capital_adequacy_ratio") == ("percent", ["Unit '%' read as percent."])
    assert normalize("18.74%", "percent", "capital_adequacy_ratio") == Decimal("18.74")
    with pytest.raises(ValueError):
        normalize("18.74", "PKR thousand", "capital_adequacy_ratio")


def bank_pdf() -> list[Page]:
    from src.pdf.reader import read_pdf
    rows = "\n".join(f"Other line {i}   {i},234,567   {i},111,222" for i in range(1, 16))
    doc = pymupdf.open()
    texts = [
        "CONSOLIDATED STATEMENT OF FINANCIAL POSITION\nAS AT DECEMBER 31, 2024\nAdvances  9  1,234,567  1,111,111\n"
        "Deposits and other accounts  16  2,345,678  2,222,222\n" + rows,
        "CONSOLIDATED STATEMENT OF PROFIT AND LOSS ACCOUNT\nFOR THE YEAR ENDED DECEMBER 31, 2024\n" + rows,
        "CONSOLIDATED CASH FLOW STATEMENT\nFOR THE YEAR ENDED DECEMBER 31, 2024\n" + rows,
        "NOTES TO THE CONSOLIDATED FINANCIAL STATEMENTS\n8. INVESTMENTS\n" + rows,
        "9. ADVANCES\nAdvances - gross 1,300,000\n" + rows, "9.1 Particulars\n" + rows, "9.2 Non-performing\n" + rows,
        "9.3 Provisions\n" + rows, "10. FIXED ASSETS\n" + rows,
        "16. DEPOSITS AND OTHER ACCOUNTS\nCurrent deposits 1  Savings deposits 2\n" + rows, "16.1 By sector\n" + rows,
        "40. CAPITAL ADEQUACY, LEVERAGE RATIO & LIQUIDITY REQUIREMENTS\nTotal capital ratio 18.74%\n" + rows, "40.1 Leverage\n" + rows,
        "ANNEXURE I: ISLAMIC BANKING BUSINESS\nSTATEMENT OF FINANCIAL POSITION\nAS AT DECEMBER 31, 2024\n" + rows,
    ]
    for text in texts:
        doc.new_page().insert_text((40, 40), text, fontsize=7)
    return read_pdf(doc.tobytes())[0]


def test_bank_pages_include_notes_found_by_their_numbers():
    from src.pdf.reader import candidate_pages, statement_title
    pages = bank_pdf()
    assert candidate_pages(pages, "consolidated", sector="bank") == [1, 2, 3, 5, 6, 7, 8, 10, 11, 12, 13]
    assert candidate_pages(pages, "consolidated") == [1, 2, 3]                 # companies never get bank notes
    assert statement_title(pages[13].text) == ""                              # Islamic banking annexure is not a primary statement


def test_ai_gets_bank_guidance_and_bank_claims_are_checked():
    from src.ai.client import AIError
    from src.ai.council import BANK_FOCUS, analysis_payload, is_bank, policy, reference_registry, validate_claim
    from src.models import Claim
    run = bank_run()
    payload = analysis_payload(run)
    assert is_bank(run) and "This company is a bank" in policy(run) and "asset quality" in BANK_FOCUS["Credit Risk Analyst"]
    assert "Advances / Islamic Financing (net) is LESS than Deposits and Other Accounts." in payload["verified_comparisons"]
    registry = reference_registry(run)
    with pytest.raises(AIError, match="contradicts"):
        validate_claim(Claim(kind="FACT", text="Advances exceed deposits.", references=["field:deposits"]), registry)
    validate_claim(Claim(kind="FACT", text="Deposits increased, as shown by metric:deposits_growth."), registry)
    with pytest.raises(AIError, match="contradicts"):
        validate_claim(Claim(kind="FACT", text="Deposits declined during the year.", references=["field:deposits"]), registry)


def test_saved_company_runs_default_to_the_company_catalogue():
    assert Company(name="X", financial_year=2024).sector == "general"


def test_provision_sign_follows_the_profit_lines_either_side():
    from src.extraction.service import PROVISION_NOTE, orient_provisions

    def found(before, provisions, after):
        return {k: FinancialField(field_name=k, normalized_value=Decimal(v))
                for k, v in (("profit_before_provisions", before), ("provisions", provisions), ("profit_before_tax", after))}
    reversal = found(1000, 40, 1040)            # "net reversal" printed without brackets
    orient_provisions(reversal)
    assert reversal["provisions"].normalized_value == -40 and PROVISION_NOTE in reversal["provisions"].notes
    charge = found(1000, -40, 960)              # a charge printed in brackets
    orient_provisions(charge)
    assert charge["provisions"].normalized_value == 40
    for unchanged in (found(1000, 40, 960), found(1000, 40, 1000), found(1000, -30, 960)):
        before = unchanged["provisions"].normalized_value
        orient_provisions(unchanged)            # already right, or not an exact match: left for review
        assert unchanged["provisions"].normalized_value == before and not unchanged["provisions"].notes


def test_npl_allowance_is_stored_positive_and_gross_advances_are_checked():
    from src.extraction.service import EXPENSE_NOTE, apply_expense_convention
    from src.validation.accounting import validate_run
    assert apply_expense_convention("npl_provisions", Decimal(-300)) == (Decimal(300), [EXPENSE_NOTE])
    assert not any("Gross advances are below" in w for w in validate_run(bank_run()))
    assert any("Gross advances are below" in w for w in validate_run(bank_run(gross_advances=4900)))


def test_share_count_far_from_eps_is_flagged():
    from src.validation.accounting import validate_run
    assert validate_run(bank_run()) == []                                      # 120 / 20 = 6 = reported EPS
    assert any("share count" in w for w in validate_run(bank_run(number_of_shares=200)))   # e.g. rupee share capital
    assert not any("share count" in w for w in validate_run(bank_run(number_of_shares=26)))  # within the loose band


def test_swapped_reference_prefix_is_repaired_not_rejected():
    from src.ai.client import AIError
    from src.ai.council import reference_registry, render_text, validate_claim
    from src.models import Claim
    run = bank_run()
    from src.calculations.ratios import calculate
    run.metrics = calculate(run)
    registry = reference_registry(run)
    claim = Claim(kind="FACT", text="The bank reported net profit of metric:net_profit.", references=["field:return_on_equity"])
    validate_claim(claim, registry)
    assert claim.references == ["metric:return_on_equity", "field:net_profit"] and "field:net_profit" in claim.text
    assert "metric:" not in render_text(claim.text, registry)
    with pytest.raises(AIError, match="unknown financial reference"):     # a name that exists nowhere is still rejected
        validate_claim(Claim(kind="FACT", text="Profit was metric:net_income.", references=[]), registry)


def test_bank_values_render_in_their_own_units():
    from src.ai.council import short_value
    assert short_value("capital_adequacy_ratio", Decimal("18.74")) == "18.74%"
    assert short_value("provisions", Decimal(-7641419000)) == "a net reversal of PKR 7.64 billion"
    assert short_value("provisions", Decimal(4880000000)) == "PKR 4.88 billion"


def test_benchmark_caveat_written_as_fact_becomes_a_limitation():
    from src.ai.client import AIError
    from src.ai.council import reference_registry, validate_claim
    from src.models import Claim
    registry = reference_registry(bank_run())
    for text in ("There is insufficient benchmark information to evaluate industry positioning.",
                 "Operating cash flow includes deposit and lending movements, so do not judge cash conversion from it."):
        claim = Claim(kind="FACT", text=text, references=[])
        validate_claim(claim, registry)
        assert claim.kind == "LIMITATION"
    with pytest.raises(AIError, match="missing a supporting reference"):   # any other unsupported fact is still rejected
        validate_claim(Claim(kind="FACT", text="The bank leads its peers.", references=[]), registry)


def test_value_under_another_label_and_unsupported_changes_are_rejected():
    from src.ai.client import AIError
    from src.ai.council import reference_registry, validate_claim
    from src.calculations.ratios import calculate
    from src.models import Claim
    run = bank_run()
    run.metrics = calculate(run)
    registry = reference_registry(run)

    def check(text, refs=()):
        validate_claim(Claim(kind="FACT", text=text, references=list(refs)), registry)
    with pytest.raises(AIError, match="places the value of Total Assets after 'total liabilities'"):
        check("The bank reported total assets of field:total_assets, total liabilities of field:total_assets.")
    with pytest.raises(AIError, match="without verified prior-year data"):    # no prior-year provisions are captured
        check("Credit loss allowance or provisions increased to field:provisions.")
    with pytest.raises(AIError, match="without verified prior-year data"):
        check("Net profit rose, alongside higher credit loss provisions field:provisions.", ["field:net_profit"])
    with pytest.raises(AIError, match="contradicts"):                       # total assets rose from 9,000 to 10,000
        check("Total assets decreased to field:total_assets.")
    # Correct labels, own-label wording and supported directions pass.
    check("Total assets increased to field:total_assets from field:total_assets_prior_year, and total liabilities "
          "were field:total_liabilities.")
    check("Non-performing advances were field:non_performing_loans against credit loss allowance held against "
          "non-performing advances of field:npl_provisions, while current and savings deposits were field:casa_deposits.")
    check("Provisions of field:provisions were charged while net profit increased.", ["field:net_profit"])


def test_stability_language_needs_benchmarks():
    from src.ai.client import AIError
    from src.ai.council import reference_registry, validate_claim
    from src.models import Claim
    with pytest.raises(AIError, match="evaluative word 'stable'"):
        validate_claim(Claim(kind="INTERPRETATION", text="The bank shows stable asset quality.",
                             references=["field:non_performing_loans"]), reference_registry(bank_run()))


def test_bank_run_renders_on_every_screen(tmp_path, monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("FINSIGHT_DB_PATH", str(tmp_path / "runs.sqlite3"))
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=20)
    app.session_state["run"] = bank_run()
    app.run()
    for step in ("2 · Extract", "3 · Verify", "4 · Results", "5 · Evaluate"):
        app.radio(key="step").set_value(step).run()
        assert not app.exception, step
        if step == "4 · Results":
            labels = {m.label for m in app.metric}
            assert {"Total income · PKR m", "Advances to Deposits (ADR)", "Capital Adequacy Ratio (reported)"} <= labels
