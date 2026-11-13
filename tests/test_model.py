"""Financial model: defaults from verified figures, forecast and DCF arithmetic, checks, Excel formulas, report, AI."""
import json
import re
from decimal import Decimal
from io import BytesIO
import pytest
from openpyxl import load_workbook
from src.calculations.model import (PLACEHOLDER_GROWTH, PLACEHOLDER_RATE, build, defaults, unavailable)
from src.calculations.ratios import calculate
from src.models import Run
from tests.test_bank import bank_run
from tests.test_broker import company_run

M = Decimal(10) ** 6


def modelled(**changes) -> Run:
    """The synthetic company (PKR m: sales 1000, gross profit 350, PBT 150, finance cost 30, tax 45, 10 m shares)."""
    run = company_run()
    run.model_assumptions = defaults(run).model_copy(update={"depreciation": Decimal("0.05"), **changes})
    return run


def test_defaults_come_from_the_verified_year():
    a = defaults(company_run())
    assert a.sales_growth == Decimal(100) / 900 and a.gross_margin == Decimal("0.35")
    assert a.operating_costs == Decimal("0.17")          # (350 - 150 - 30) / 1000
    assert a.finance_cost == 30 * M and a.tax_rate == Decimal("0.3") and a.capex == Decimal("0.08")
    assert a.working_capital == Decimal("0.33")          # (150 receivables + 180 inventory) / 1000
    assert a.net_debt == 280 * M                          # 400 debt - 120 cash
    assert a.depreciation is None                         # not extracted: the analyst types it
    assert (a.discount_rate, a.terminal_growth) == (PLACEHOLDER_RATE, PLACEHOLDER_GROWTH)


def test_forecast_matches_a_hand_calculation():
    year = build(modelled(sales_growth=Decimal("0.10"))).cases["Base"][0]
    # Sales 1100; gross profit 385; costs 187; EBIT 198; PBT 168; tax 50.4; net 117.6
    assert year.year == 2026 and year.revenue == 1100 * M and year.ebit == 198 * M
    assert year.net_profit == Decimal("117.6") * M and year.eps == Decimal("11.76")
    # NOPAT 138.6 + depreciation 55 - capex 88 - working capital 0.33 x 100 = 72.6
    assert year.free_cash_flow == Decimal("72.6") * M


def test_value_per_share_matches_the_textbook_formula():
    model = build(modelled())
    fcf = [float(y.free_cash_flow) for y in model.cases["Base"]]
    r, g = 0.18, 0.05
    enterprise = sum(f / (1 + r) ** t for t, f in enumerate(fcf, 1)) + fcf[-1] * (1 + g) / (r - g) / (1 + r) ** 5
    assert float(model.values["Base"].per_share) == pytest.approx((enterprise - 280e6) / 10e6, rel=1e-12)
    assert 0 < model.values["Base"].terminal_share < 1


def test_cases_grid_and_range_move_the_right_way():
    model = build(modelled(shock_share=Decimal("0.4"), shock_change=Decimal("0.15")))
    v = {k: x.per_share for k, x in model.values.items()}
    assert v["Downside"] < v["Base"] < v["Upside"] and v["Base + input-cost shock"] < v["Base"]
    shock_year = model.cases["Base + input-cost shock"][0]   # margin 0.35 - 0.65 x 0.4 x 0.15 = 0.311
    assert shock_year.gross_profit / shock_year.revenue == Decimal("0.311")
    assert len(model.grid) == 5 and all(len(row) == 3 for _, row in model.grid)
    for _, row in model.grid:                                  # more long-term growth, more value
        assert row[0][1] < row[1][1] < row[2][1]
    column = [row[1][1] for _, row in model.grid]              # a higher discount rate, less value
    assert column == sorted(column, reverse=True)
    assert model.grid[2][1][1][1] == v["Base"]                 # the centre of the grid is the base case
    cells = [x for _, row in model.grid for _, x in row]
    assert model.value_range == (min(cells), max(cells))


def test_missing_inputs_hold_back_only_what_needs_them():
    run = company_run()
    model = build(run)                                         # no depreciation yet
    assert model.cases["Base"][0].free_cash_flow is None and not model.values and model.value_range is None
    assert "Depreciation and amortisation (% of sales)" in model.missing
    run.model_assumptions = defaults(run).model_copy(update={"sales_growth": None})
    assert build(run).cases == {}


def test_discount_rate_must_be_above_long_term_growth():
    model = build(modelled(discount_rate=Decimal("0.05"), terminal_growth=Decimal("0.06")))
    assert model.values["Base"].per_share is None and "above long-term growth" in model.values["Base"].reason
    assert any("must be above long-term growth" in c for c in model.checks)


def test_checks_flag_assumptions_far_from_the_report():
    checks = " ".join(build(modelled(sales_growth=Decimal("0.40"), gross_margin=Decimal("0.45"), tax_rate=Decimal("0.05"),
                                     depreciation=Decimal("0.10"))).checks)
    assert "far from last year's 11.11%" in checks and "gross margin" in checks.lower()
    assert "effective rate" in checks and "asset base shrinks" in checks and "placeholders" in checks
    own = build(modelled(discount_rate=Decimal("0.2"), terminal_growth=Decimal("0.04"))).checks
    assert not any("placeholder" in c for c in own)
    late = build(modelled(discount_rate=Decimal("0.08"), terminal_growth=Decimal("0.06")))
    assert any("comes after year 5" in c for c in late.checks)


def test_banks_get_no_model_and_the_reason_says_why():
    from src.reporting.excel import run_workbook
    run = bank_run()
    assert "Banks need a different model" in unavailable(run)
    with pytest.raises(ValueError):
        build(run)
    run.metrics = calculate(run)
    assert "Model" not in load_workbook(BytesIO(run_workbook(run))).sheetnames


def test_the_ai_never_sees_the_model():
    from src.ai.council import analysis_payload
    run = modelled()
    payload = json.dumps(analysis_payload(run), default=str)
    assert "discount_rate" not in payload and "model_assumptions" not in payload


def test_assumptions_are_saved_with_the_run():
    run = modelled(in_report=True)
    again = Run.model_validate_json(run.model_dump_json())
    assert again.model_assumptions == run.model_assumptions


class Blank(float):
    """An empty cell: zero in arithmetic, but still recognisable as empty for COUNTBLANK."""


def excel_value(book, sheet: str, coordinate: str, seen: dict):
    """Evaluate a cell of a BrokerLens workbook in Python: references, + - * / ^, MAX, SUM, IF, OR and COUNTBLANK."""
    if (sheet, coordinate) in seen:
        return seen[(sheet, coordinate)]
    raw = book[sheet][coordinate].value
    if not (isinstance(raw, str) and raw.startswith("=")):
        seen[(sheet, coordinate)] = Blank() if raw is None else raw   # Excel reads an empty cell as 0
        return seen[(sheet, coordinate)]
    pattern = (r"(?:'(?P<q>[^']+)'!|(?P<s>[A-Za-z]+)!)?\$?(?P<c1>[A-Z]{1,2})\$?(?P<r1>\d+)"
               r"(?::\$?(?P<c2>[A-Z]{1,2})\$?(?P<r2>\d+))?")

    def ref(m):
        where = m.group("q") or m.group("s") or sheet
        if m.group("c2"):
            cols = [chr(c) for c in range(ord(m.group("c1")), ord(m.group("c2")) + 1)]
            return "[" + ",".join(f"_v({where!r},'{c}{m.group('r1')}')" for c in cols) + "]"
        return f"_v({where!r},'{m.group('c1')}{m.group('r1')}')"

    expr = re.sub(pattern, ref, raw[1:]).replace("^", "**").replace('""', "None")
    expr = re.sub(r"\bIF\(", "_if(", expr).replace("COUNTBLANK(", "_blank(").replace("OR(", "_or(")
    expr = expr.replace("MAX(", "max(").replace("SUM(", "sum(")
    env = {"_v": lambda s, c: excel_value(book, s, c, seen), "_if": lambda c, a, b: a if c else b,
           "_or": lambda *x: any(x), "_blank": lambda xs: sum(isinstance(x, Blank) for x in xs), "max": max, "sum": sum,
           "__builtins__": {}}
    seen[(sheet, coordinate)] = result = eval(expr, env)
    return result


def test_excel_model_formulas_reproduce_python():
    from src.reporting.excel import run_workbook
    run = modelled(shock_share=Decimal("0.4"), shock_change=Decimal("0.15"))
    run.metrics = calculate(run)
    model = build(run)
    book = load_workbook(BytesIO(run_workbook(run)))
    sheet, seen = book["Model"], {}
    labels = {row[0].value: row[0].row for row in sheet.iter_rows() if isinstance(row[0].value, str)}
    years = model.cases["Base"]
    for label, attr in [("Sales", "revenue"), ("Net profit", "net_profit"), ("EPS (PKR)", "eps"),
                        ("Free cash flow to the firm", "free_cash_flow")]:
        for col, year in zip("CDEFG", years):
            assert excel_value(book, "Model", f"{col}{labels[label]}", seen) == pytest.approx(float(getattr(year, attr)), rel=1e-9)
    per_share = excel_value(book, "Model", f"B{labels['Value per share (PKR), base case']}", seen)
    assert per_share == pytest.approx(float(model.values["Base"].per_share), rel=1e-9)
    assert sheet[f"B{labels['BrokerLens (Python) value per share, for checking']}"].value == pytest.approx(per_share)
    head = labels["Value per share (PKR): discount rate down, long-term growth across"]
    for i, (rate, row) in enumerate(model.grid, start=1):
        assert excel_value(book, "Model", f"A{head + i}", seen) == pytest.approx(float(rate))
        for col, (_, value) in zip("BCD", row):
            assert excel_value(book, "Model", f"{col}{head + i}", seen) == pytest.approx(float(value), rel=1e-9)
    assert sheet[f"B{labels['Sales growth a year']}"].fill.fgColor.rgb.endswith("FFF2CC")   # an editable input cell


def test_report_shows_the_model_only_when_the_analyst_adds_it():
    from src.reporting.export import markdown_report
    run = modelled()
    run.metrics = calculate(run)
    assert "Financial model" not in markdown_report(run)
    run.model_assumptions.in_report = True
    report = markdown_report(run)
    assert "### Financial model (analyst assumptions)" in report and "Value per share range, base case" in report
    assert "not a target price" in report


def test_excel_value_stays_empty_until_every_assumption_is_filled():
    from src.reporting.excel import run_workbook
    run = company_run()                      # depreciation not typed yet
    run.metrics = calculate(run)
    book = load_workbook(BytesIO(run_workbook(run)))
    labels = {row[0].value: row[0].row for row in book["Model"].iter_rows() if isinstance(row[0].value, str)}
    assert excel_value(book, "Model", f"B{labels['Value per share (PKR), base case']}", {}) is None
    head = labels["Value per share (PKR): discount rate down, long-term growth across"]
    assert excel_value(book, "Model", f"C{head + 3}", {}) is None

