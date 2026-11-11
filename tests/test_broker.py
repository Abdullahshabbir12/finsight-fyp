"""Broker features: valuation from a user-supplied price, Excel with live formulas, peer comparison, PDF highlights."""
import re
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import pymupdf
import pytest
from openpyxl import load_workbook
from tests.test_bank import bank_run
from src.calculations.ratios import market_metrics
from src.demo import demo_run
from src.validation.review import accept_ready, commit_review, mark_remaining_unavailable, review_rows


def company_run():
    run = demo_run()
    rows = review_rows(run)
    accept_ready(run, rows)
    mark_remaining_unavailable(rows, "Not reported in this document")
    commit_review(run, rows)
    return run


def priced(run, price="150", dps="7.5"):
    run.company.share_price, run.company.dividend_per_share = Decimal(price), Decimal(dps)
    return run


def test_valuation_multiples_use_the_typed_price_and_verified_values():
    m = {x.name: x for x in market_metrics(priced(bank_run()))}       # EPS 6, equity 800, 20 shares
    assert m["price_to_earnings"].value == 25 and m["price_to_book"].value == Decimal(150) / 40
    assert m["market_capitalisation"].value == 3000 and m["dividend_yield"].value == Decimal("0.05")
    assert "not verified" in m["price_to_earnings"].reason
    unpriced = {x.name: x for x in market_metrics(bank_run())}
    assert all(x.value is None and "share price" in x.reason for x in unpriced.values())
    loss = {x.name: x for x in market_metrics(priced(bank_run(eps=-2)))}
    assert loss["price_to_earnings"].value is None and "not meaningful" in loss["price_to_earnings"].reason


def test_the_ai_never_receives_the_share_price():
    from src.ai.council import analysis_payload
    run = priced(bank_run())
    assert "share_price" not in analysis_payload(run)["company"] and "dividend_per_share" not in run.company.profile()
    assert run.company.model_dump()["share_price"] == 150      # still saved with the run


def evaluate(formula: str, cells: dict[str, float], price: float | None = None, dps: float | None = None) -> float:
    """Evaluate a FinSight Excel formula in Python by substituting the referenced cells."""
    expr = formula.lstrip("=")
    expr = re.sub(r"'Verified data'!\$B\$(\d+)", lambda m: repr(cells[int(m.group(1))]), expr)
    expr = expr.replace("Summary!$B$10", repr(price)).replace("Summary!$B$11", repr(dps))
    match = re.fullmatch(r'IF\((?:OR\()?(.*?)\)?,"",(.*)\)', expr)
    if match:  # the valuation guards: blank when the price is missing or EPS/equity is not positive
        expr = match.group(2)
    return eval(expr, {"__builtins__": {}})  # arithmetic only: numbers, + - * / and brackets


@pytest.mark.parametrize("make", [bank_run, company_run])
def test_excel_formulas_reproduce_every_python_ratio(make):
    from src.calculations.ratios import calculate
    from src.reporting.excel import run_workbook
    run = priced(make())
    run.metrics = calculate(run)
    book = load_workbook(BytesIO(run_workbook(run)))
    assert {"Summary", "Verified data", "Ratios"} <= set(book.sheetnames)
    data = book["Verified data"]
    cells = {row[0].row: row[1].value for row in data.iter_rows(min_row=2) if row[1].value is not None}
    checked = 0
    for metric, formula, python, *_ in book["Ratios"].iter_rows(min_row=2, values_only=True):
        if isinstance(formula, str) and formula.startswith("="):
            assert evaluate(formula, cells, 150.0, 7.5) == pytest.approx(python, rel=1e-12), metric
            checked += 1
    assert checked >= 12
    assert book["Summary"]["B10"].value == 150 and book["Summary"]["B11"].value == 7.5


def test_peer_comparison_lines_up_runs_of_one_type():
    from src.reporting.excel import display_peer, peer_rows, peer_workbook
    a, b = bank_run(), bank_run(net_profit=150, tax_expense=50)
    b.company.ticker = "OTHR"
    rows = peer_rows([a, b])
    roe = next(r for r in rows if r["Metric"] == "Return on Equity")
    assert roe["Synthetic Bank FY2024"] == Decimal("0.15") and roe["OTHR FY2024"] == Decimal(150) / 800
    shown = display_peer(rows)
    assert next(r for r in shown if r["Metric"] == "Return on Equity")["OTHR FY2024"] == "18.75%"
    assert load_workbook(BytesIO(peer_workbook([a, b])))["Peer comparison"].max_row > 10
    with pytest.raises(ValueError, match="one company type"):
        peer_rows([a, company_run()])


def statement_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    lines = ["STATEMENT OF FINANCIAL POSITION", "Investments        10     4,000,000     3,500,000",
             "Advances           11     4,700,000     4,000,000", "Deposits           16     8,000,000     7,200,000"]
    for i, line in enumerate(lines):
        page.insert_text((40, 60 + 20 * i), line, fontsize=10)
    return doc.tobytes()


def test_highlight_finds_the_figure_on_its_labelled_line():
    from src.pdf.reader import highlight_page
    pdf = statement_pdf()
    # 4,000,000 is printed twice; the label picks the Investments line, not the prior-year advances.
    full, close, found = highlight_page(pdf, 1, ["4,000,000"], "Investments 10 4,000,000 3,500,000")
    assert found and close.startswith(b"\x89PNG") and full.startswith(b"\x89PNG")
    _, close, found = highlight_page(pdf, 1, ["9,999,999"], "Nothing")
    assert not found and close is None


def test_highlight_target_follows_an_edited_value():
    from src.validation.review import evidence_target
    run = bank_run()
    review = next(r for r in run.reviews if r.field_name == "advances_net")
    review.decision, review.verified_value, review.source_page = "edit", Decimal(4700000000), 1
    advances = next(f for f in run.fields if f.field_name == "advances_net")
    advances.unit = "PKR thousand"
    page, numbers, _ = evidence_target(run, "advances_net")
    assert page == 1 and numbers[0] == "4,700,000"          # the printed form in the statement's own unit


def test_reports_show_valuation_only_when_priced():
    from src.calculations.ratios import calculate
    from src.reporting.export import markdown_report
    run = bank_run()
    run.metrics = calculate(run)
    assert "Valuation multiples" not in markdown_report(run)
    assert "| Price / Earnings (P/E) | 25.00x |" in markdown_report(priced(run))


def test_results_screen_with_price_and_comparison(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src.database.store import save_run
    monkeypatch.setenv("FINSIGHT_DB_PATH", str(tmp_path / "runs.sqlite3"))
    other = bank_run(net_profit=150, tax_expense=50)
    other.id, other.company.name = "peer", "Peer Bank"
    save_run(other)
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=30)
    app.session_state["run"] = bank_run(provisions=-50, profit_before_tax=300, tax_expense=180)  # one finding
    app.run()
    app.radio(key="step").set_value("4 · Results").run()
    assert not app.exception
    app.number_input(key="price_bank-test").set_value(150.0).run()
    assert not app.exception
    assert any(m.label == "Price / Earnings (P/E)" and m.value == "25.00x" for m in app.metric)
    assert any("1 finding to review" in md.value for md in app.markdown)
    assert any("Profit includes a net provision reversal" in e.label for e in app.expander)
    next(b for b in app.button if b.key == "decide_bank-test_provision_reversal").click().run()
    assert any("Choose a status first" in e.value for e in app.error)          # nothing is preselected
    app.radio(key="status_bank-test_provision_reversal").set_value("dismissed").run()
    next(b for b in app.button if b.key == "decide_bank-test_provision_reversal").click().run()
    assert any("Explain why" in e.value for e in app.error)                     # dismissing needs a reason
    app.text_area(key="comment_bank-test_provision_reversal").set_value("One-off recovery, note 33")
    next(b for b in app.button if b.key == "decide_bank-test_provision_reversal").click().run()
    assert not app.exception
    decision = app.session_state.run.finding_decisions["provision_reversal"][-1]
    assert decision.status == "dismissed" and decision.comment == "One-off recovery, note 33"
    assert any("Dismissed" in e.label for e in app.expander)
    app.multiselect(key="peers_bank-test").set_value(["peer"]).run()
    assert not app.exception
    labels = {b.label for b in app.get("download_button")}
    assert {"Download Excel", "Download comparison (Excel)"} <= labels
