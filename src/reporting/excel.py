"""Excel workbooks for analysts: verified data with evidence, ratios as live formulas, and peer comparison.

Each ratio is written as an Excel formula over the verified-data cells, beside BrokerLens's own Python result, so an
analyst can audit the arithmetic or change an input. The price cells start with the user's price (or empty) and can
be edited in Excel; the valuation multiples then recalculate.
"""
from decimal import Decimal
from io import BytesIO
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet
from src.ai.council import reference_registry, render_text
from src.calculations.model import (AMOUNTS as MODEL_AMOUNTS, GROWTH_STEPS, LABELS as MODEL_LABELS, LIMITATIONS, NOT_ADVICE,
                                    RATE_STEPS, YEARS, basis, build, cases, unavailable)
from src.calculations.ratios import ALL_GROWTH, ALL_SPECS, AVERAGE, calculate, display_metric, market_metrics
from src.catalog import LABELS, catalog, internal_unit
from src.models import Metric, Run
from src.reporting.charts import year_pairs
from src.validation.accounting import STATUS_LABEL, by_priority, current_decision, findings
from src.validation.review import verified_values

DATA = "Verified data"
HEADER = PatternFill("solid", fgColor="E4EFE8")
INPUT = PatternFill("solid", fgColor="FFF2CC")
NOTICE = ("Decision-support output for research. Values were verified by the user against the annual report; "
          "this is not an audit and not investment advice. Share price and dividend inputs are user-supplied.")
FORMATS = {"percent": "0.00%", "multiple": '0.00"x"', "amount": '#,##0'}


def number_format(key: str) -> str:
    unit = internal_unit(key)
    return "0.00" if unit in ("PKR/share", "%") else "#,##0"


def header(sheet: Worksheet, titles: list[str], widths: list[int]) -> None:
    sheet.append(titles)
    for i, (cell, width) in enumerate(zip(sheet[sheet.max_row], widths), start=1):
        cell.font, cell.fill = Font(bold=True), HEADER
        sheet.column_dimensions[cell.column_letter].width = width
    sheet.freeze_panes = f"A{sheet.max_row + 1}"  # a string, so no empty row is created below the header


def ratio_formula(name: str, ref: dict[str, str]) -> str:
    """The Excel version of a BrokerLens ratio, built from the same definitions as the Python calculation."""
    if name in ALL_SPECS:
        spec = ALL_SPECS[name]
        numerator = " - ".join(ref[k] for k in spec.numerator)
        parts = spec.denominator if isinstance(spec.denominator, tuple) else (spec.denominator,)
        return f"=({numerator})/({' + '.join(ref[k] for k in parts)})"
    if name in ALL_GROWTH:
        field = ALL_GROWTH[name][1]
        current, prior = ref[field], ref[field + "_prior_year"]
        return f"=({current} - {prior})/{prior}"
    if name in AVERAGE:
        _, numerator, balance, _ = AVERAGE[name]
        top = " - ".join(ref[k] for k in (numerator if isinstance(numerator, tuple) else (numerator,)))
        return f"=({top})/(({ref[balance]} + {ref[balance + '_prior_year']})/2)"
    if name == "capital_adequacy":
        return f"={ref['capital_adequacy_ratio']}/100"
    raise KeyError(name)


def market_formula(name: str, ref: dict[str, str], price: str, dps: str) -> str | None:
    """Live valuation formulas; blank until a price is entered. None when a verified input is unavailable."""
    needs = {"price_to_earnings": ["eps"], "price_to_book": ["equity", "number_of_shares"],
             "market_capitalisation": ["number_of_shares"], "dividend_yield": []}[name]
    if any(k not in ref for k in needs):
        return None
    return {"price_to_earnings": f'=IF(OR({price}="",{ref.get("eps")}<=0),"",{price}/{ref.get("eps")})',
            "price_to_book": f'=IF(OR({price}="",{ref.get("equity")}<=0),"",{price}/({ref.get("equity")}/{ref.get("number_of_shares")}))',
            "market_capitalisation": f'=IF({price}="","",{price}*{ref.get("number_of_shares")})',
            "dividend_yield": f'=IF(OR({price}="",{dps}=""),"",{dps}/{price})'}[name]


def as_number(value: Decimal | None):
    return None if value is None else float(value)


def run_workbook(run: Run) -> bytes:
    values = verified_values(run)
    metrics = run.metrics or calculate(run)
    c = run.company
    book = Workbook()
    summary = book.active
    summary.title = "Summary"
    summary.column_dimensions["A"].width, summary.column_dimensions["B"].width = 34, 70
    rows = [("BrokerLens analysis", ""), ("Company", c.name), ("Ticker", c.ticker), ("Financial year", c.financial_year),
            ("Statement basis", c.statement_basis.title()), ("Company type", "Bank" if c.sector == "bank" else "Non-financial"),
            ("Source document", run.filename), ("Verification saved", run.verified_at or ""), ("", ""),
            ("Share price, PKR (user-supplied; edit me)", as_number(c.share_price)),
            ("Dividend per share, PKR (user-supplied; edit me)", as_number(c.dividend_per_share)),
            ("Price date", c.price_date), ("", ""), ("Notice", NOTICE)]
    for row in rows:
        summary.append(list(row))
    summary["A1"].font = Font(bold=True, size=14)
    for cell in ("B10", "B11"):
        summary[cell].fill, summary[cell].number_format = INPUT, "#,##0.00"
    summary["B14"].alignment = Alignment(wrap_text=True)
    price, dps = "Summary!$B$10", "Summary!$B$11"
    cards = by_priority(findings(run))
    summary.append([])
    summary.append(["Findings", f"{len(cards)} from the accounting checks, see the Findings sheet (prompts for review, "
                    "not conclusions)"])
    summary.cell(row=summary.max_row, column=1).font = Font(bold=True)
    sheet = book.create_sheet("Findings")
    header(sheet, ["Priority", "Category", "Finding", "Detail", "Calculation", "Figures", "Why it matters", "What to check next",
                   "Analyst decision", "Comment", "Decided"], [10, 18, 40, 70, 60, 40, 60, 70, 20, 50, 18])
    for card in cards:
        decision, changed = current_decision(run, card)
        sheet.append([card.priority.title(), card.category, card.title, card.detail, card.calculation,
                      ", ".join(LABELS[k] for k in card.fields), card.why, "\n".join(card.next_steps),
                      STATUS_LABEL[decision.status if decision else "open"] + (" (figures changed since)" if changed else ""),
                      decision.comment if decision else "", decision.at[:16].replace("T", " ") if decision else ""])
        for cell in sheet[sheet.max_row]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    data = book.create_sheet(DATA)
    header(data, ["Field", "Value", "Unit", "Year", "Decision", "PDF page", "Evidence (quote)", "Review note", "Key"],
           [44, 22, 12, 8, 12, 9, 70, 50, 30])
    reviews = {r.field_name: r for r in run.reviews}
    ref = {}
    for key in catalog(c.sector):
        r = reviews[key]
        data.append([LABELS[key], as_number(values.get(key)), internal_unit(key), r.reporting_year, r.decision,
                     r.source_page, r.source_text, r.explanation(), key])
        row = data.max_row
        data.cell(row=row, column=2).number_format = number_format(key)
        if key in values:
            ref[key] = f"'{DATA}'!$B${row}"

    sheet = book.create_sheet("Ratios")
    header(sheet, ["Metric", "Excel formula result", "BrokerLens (Python) result", "Definition", "Note / N/A reason"],
           [44, 20, 22, 80, 60])

    def add(metric: Metric, formula: str | None) -> None:
        sheet.append([metric.label, formula, as_number(metric.value), metric.formula, metric.reason])
        row = sheet.max_row
        for column in (2, 3):
            sheet.cell(row=row, column=column).number_format = FORMATS[metric.format]

    for metric in metrics:
        add(metric, ratio_formula(metric.name, ref) if metric.value is not None else None)
    sheet.append([])
    sheet.append(["Valuation (from the share price on the Summary sheet)"])
    sheet.cell(row=sheet.max_row, column=1).font = Font(bold=True)
    for metric in market_metrics(run):
        add(metric, market_formula(metric.name, ref, price, dps))

    if not unavailable(run):
        model_sheet(book, run, ref)

    pairs, unit = year_pairs(run)
    if pairs:
        chart_sheet = book.create_sheet("Charts")
        year = c.financial_year
        header(chart_sheet, ["Figure", f"FY{year - 1} ({unit})", f"FY{year} ({unit})"], [44, 18, 18])
        for i in range(0, len(pairs), 2):
            chart_sheet.append([pairs[i]["Figure"], pairs[i]["Amount"], pairs[i + 1]["Amount"]])
            for cell in chart_sheet[chart_sheet.max_row][1:]:
                cell.number_format = "#,##0.00"
        chart = BarChart()
        chart.type, chart.title, chart.y_axis.title = "bar", "This year vs last year", unit
        rows = chart_sheet.max_row
        chart.add_data(Reference(chart_sheet, min_col=2, max_col=3, min_row=1, max_row=rows), titles_from_data=True)
        chart.set_categories(Reference(chart_sheet, min_col=1, min_row=2, max_row=rows))
        chart.height, chart.width = 9, 18
        chart_sheet.add_chart(chart, "E2")

    if run.analysts or run.synthesis:
        registry = reference_registry(run)
        ai = book.create_sheet("AI analysis")
        header(ai, ["Perspective / section", "Kind", "Statement (values inserted by Python)", "Sources"], [30, 16, 110, 50])
        for role, result in run.analysts.items():
            for claim in [result.overall_observation, *result.positive_factors, *result.risk_factors, *result.limitations]:
                ai.append([role, claim.kind, render_text(claim.text, registry), ", ".join(claim.references)])
        for section in run.synthesis.sections if run.synthesis else []:
            for claim in section.claims:
                ai.append(["Synthesis: " + section.heading, claim.kind, render_text(claim.text, registry), ", ".join(claim.references)])
        for row in ai.iter_rows(min_row=2, min_col=3, max_col=3):
            row[0].alignment = Alignment(wrap_text=True, vertical="top")
    output = BytesIO()
    book.save(output)
    return output.getvalue()


MODEL_ORDER = ["sales_growth", "gross_margin", "operating_costs", "finance_cost", "tax_rate", "capex", "depreciation",
               "working_capital", "discount_rate", "terminal_growth", "net_debt"]


def model_sheet(book: Workbook, run: Run, ref: dict[str, str]) -> None:
    """The financial model as live formulas: yellow assumption cells drive the forecast, free cash flow and value.

    Starting-year cells point at the Verified data sheet; Python's own base-case result sits beside the formula result
    so the two can be compared. Scenario values are BrokerLens results for the offsets set in the app.
    """
    model = build(run)
    a, y0 = model.assumptions, run.company.financial_year
    sheet = book.create_sheet("Model")
    sheet.column_dimensions["A"].width = 46
    for column in "BCDEFG":
        sheet.column_dimensions[column].width = 16
    sheet.append(["Financial model: your assumptions, BrokerLens arithmetic"])
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append([NOT_ADVICE + " Edit the yellow cells; starting figures link to the Verified data sheet. Amounts in PKR."])
    sheet.merge_cells("A2:G2")
    sheet["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.row_dimensions[2].height = 32
    sheet.append([])
    sheet.append(["Assumption", "Value", "Where the starting value came from"])
    for cell in sheet[sheet.max_row][:3]:
        cell.font, cell.fill = Font(bold=True), HEADER
    notes, cell = basis(run), {}
    for name in MODEL_ORDER:
        sheet.append([MODEL_LABELS[name], as_number(getattr(a, name)), notes[name]])
        row = sheet.max_row
        cell[name] = f"$B${row}"
        sheet.cell(row=row, column=2).fill = INPUT
        sheet.cell(row=row, column=2).number_format = "#,##0" if name in MODEL_AMOUNTS else "0.00%"
        sheet.merge_cells(start_row=row, start_column=3, end_row=row, end_column=7)
        sheet.cell(row=row, column=3).alignment = Alignment(wrap_text=True, vertical="top")
        sheet.row_dimensions[row].height = 30
    shares = ref.get("number_of_shares", "")
    blank = f'COUNTBLANK({cell[MODEL_ORDER[0]]}:{cell[MODEL_ORDER[-1]]})>0'  # value stays empty until every input is set
    sheet.append(["The value per share stays empty until every yellow cell is filled."])

    sheet.append([])
    sheet.append(["Forecast, base case (PKR)", f"FY{y0} (verified)", *[f"FY{y0 + t}" for t in range(1, YEARS + 1)]])
    for c in sheet[sheet.max_row]:
        c.font, c.fill = Font(bold=True), HEADER
    cols = "CDEFG"
    rows: dict[str, int] = {}

    def line(key: str, label: str, base: str | None, formula, fmt: str = "#,##0") -> None:
        """One forecast line; formula(column, previous column, year number) gives each year's Excel formula."""
        sheet.append([label])  # write the row first: after a blank row, max_row would point one row too early
        rows[key] = row = sheet.max_row
        cells = [base] + [formula(col, chr(ord(col) - 1), t) for t, col in enumerate(cols, start=1)]
        for column, content in enumerate(cells, start=2):
            sheet.cell(row=row, column=column, value=content).number_format = fmt

    def r(key: str, col: str) -> str:
        return f"{col}{rows[key]}"

    gp_base = (f"={ref['gross_profit']}" if "gross_profit" in ref else
               f"={ref['revenue']} - {ref['cost_of_sales']}" if "cost_of_sales" in ref else None)
    has_ebit = "profit_before_tax" in ref and "finance_cost" in ref
    line("sales", "Sales", f"={ref['revenue']}", lambda c, p, t: f"={p}{rows['sales']}*(1 + {cell['sales_growth']})")
    line("gp", "Gross profit", gp_base, lambda c, p, t: f"={r('sales', c)}*{cell['gross_margin']}")
    line("costs", "Operating costs, net of other income",
         f"=B{rows['gp']} - ({ref['profit_before_tax']} + {ref['finance_cost']})" if has_ebit and gp_base else None,
         lambda c, p, t: f"={r('sales', c)}*{cell['operating_costs']}")
    line("ebit", "EBIT (profit before tax + finance cost)",
         f"={ref['profit_before_tax']} + {ref['finance_cost']}" if has_ebit else None,
         lambda c, p, t: f"={r('gp', c)} - {r('costs', c)}")
    line("fc", "Finance cost", f"={ref['finance_cost']}" if "finance_cost" in ref else None,
         lambda c, p, t: f"={cell['finance_cost']}")
    line("pbt", "Profit before tax", f"={ref['profit_before_tax']}" if "profit_before_tax" in ref else None,
         lambda c, p, t: f"={r('ebit', c)} - {r('fc', c)}")
    line("tax", "Tax", f"={ref['tax_expense']}" if "tax_expense" in ref else None,
         lambda c, p, t: f"=MAX({r('pbt', c)}, 0)*{cell['tax_rate']}")
    line("np", "Net profit", f"={ref['net_profit']}" if "net_profit" in ref else None,
         lambda c, p, t: f"={r('pbt', c)} - {r('tax', c)}")
    line("eps", "EPS (PKR)", f"={ref['eps']}" if "eps" in ref else None,
         lambda c, p, t: f"={r('np', c)}/{shares}", "#,##0.00")
    line("nopat", "NOPAT (EBIT less tax on positive EBIT)", None,
         lambda c, p, t: f"={r('ebit', c)} - MAX({r('ebit', c)}, 0)*{cell['tax_rate']}")
    line("dep", "Depreciation and amortisation", None, lambda c, p, t: f"={r('sales', c)}*{cell['depreciation']}")
    line("capex", "Capital spending", f"={ref['capital_expenditure']}" if "capital_expenditure" in ref else None,
         lambda c, p, t: f"={r('sales', c)}*{cell['capex']}")
    line("wc", "Increase in working capital", None,
         lambda c, p, t: f"=({r('sales', c)} - {p}{rows['sales']})*{cell['working_capital']}")
    line("fcf", "Free cash flow to the firm", None,
         lambda c, p, t: f"={r('nopat', c)} + {r('dep', c)} - {r('capex', c)} - {r('wc', c)}")
    line("df", "Discount factor", None, lambda c, p, t: f"=1/(1 + {cell['discount_rate']})^{t}", "0.0000")
    line("pv", "Present value of free cash flow", None, lambda c, p, t: f"={r('fcf', c)}*{r('df', c)}")

    sheet.append([])
    rate, growth = cell["discount_rate"], cell["terminal_growth"]
    value_rows: dict[str, int] = {}
    steps = [("pv_years", "Present value, years 1-5", f"=SUM(C{rows['pv']}:G{rows['pv']})"),
             ("terminal", "Terminal value at year 5", f"=G{rows['fcf']}*(1 + {growth})/({rate} - {growth})"),
             ("pv_terminal", "Present value of the terminal value", f"=B{{terminal}}*G{rows['df']}"),
             ("ev", "Enterprise value", "=B{pv_years} + B{pv_terminal}"),
             ("net_debt", "Less net debt", f"={cell['net_debt']}"),
             ("equity", "Equity value", "=B{ev} - B{net_debt}"),
             ("shares", "Shares", f"={shares}"),
             ("per_share", "Value per share (PKR), base case", f'=IF(OR({blank}, {rate}<={growth}, B{{equity}}<=0), "", B{{equity}}/B{{shares}})'),
             ("terminal_share", "Share of value after year 5", '=IF(B{ev}<=0, "", B{pv_terminal}/B{ev})')]
    for key_, label, _ in steps:  # rows first, so formulas can refer to rows below them
        sheet.append([label])
        value_rows[key_] = sheet.max_row
    for key_, _, formula in steps:
        row = value_rows[key_]
        sheet.cell(row=row, column=2).value = formula.format(**value_rows)
        sheet.cell(row=row, column=2).number_format = ("#,##0.00" if key_ in ("per_share",) else "0%"
                                                       if key_ == "terminal_share" else "#,##0")
    sheet.cell(row=value_rows["per_share"], column=1).font = Font(bold=True)
    base = model.values.get("Base")
    sheet.append(["BrokerLens (Python) value per share, for checking", as_number(base.per_share) if base else None])
    sheet.cell(row=sheet.max_row, column=2).number_format = "#,##0.00"

    sheet.append([])
    sheet.append(["Value per share (PKR): discount rate down, long-term growth across",
                  *[f"={growth} + {float(s)}" for s in GROWTH_STEPS]])
    head = sheet.max_row
    for c in sheet[head]:
        c.font, c.fill = Font(bold=True), HEADER
    for c in sheet[head][1:]:
        c.number_format = "0.00%"
    fcf = [f"{col}{rows['fcf']}" for col in cols]
    for step in RATE_STEPS:
        row = sheet.max_row + 1
        k, cells = f"$A{row}", [f"={rate} + {float(step)}"]
        for col in "BCD":
            g = f"{col}${head}"
            ev = " + ".join(f"{f}/(1 + {k})^{t}" for t, f in enumerate(fcf, start=1))
            ev += f" + {fcf[-1]}*(1 + {g})/({k} - {g})/(1 + {k})^{YEARS}"
            equity = f"({ev} - {cell['net_debt']})"
            cells.append(f'=IF(OR({blank}, {k}<={g}, {equity}<=0), "", {equity}/{shares})')
        sheet.append(cells)
        sheet.cell(row=row, column=1).number_format = "0.00%"
        for c in sheet[row][1:]:
            c.number_format = "#,##0.00"

    sheet.append([])
    sheet.append(["Cases (BrokerLens results for the offsets set in the app)", "Sales growth", "Gross margin",
                  f"EPS FY{y0 + 1}", f"EPS FY{y0 + YEARS}", "Value per share"])
    for c in sheet[sheet.max_row]:
        c.font, c.fill = Font(bold=True), HEADER
    for name, (growth_shift, margin_shift, shock) in cases(a).items():
        years = model.cases.get(name)
        if not years or a.sales_growth is None:
            continue
        margin = a.gross_margin + margin_shift
        if shock:
            margin -= (1 - margin) * a.shock_share * a.shock_change
        valuation = model.values.get(name)
        sheet.append([name, as_number(a.sales_growth + growth_shift), as_number(margin), as_number(years[0].eps),
                      as_number(years[-1].eps), as_number(valuation.per_share) if valuation else None])
        for c, fmt in zip(sheet[sheet.max_row][1:], ("0.00%", "0.00%", "#,##0.00", "#,##0.00", "#,##0.00")):
            c.number_format = fmt
    sheet.append([])
    for note in ["Checks:", *model.checks, "Limits:", *LIMITATIONS]:
        sheet.append([note])
        sheet.merge_cells(start_row=sheet.max_row, start_column=1, end_row=sheet.max_row, end_column=7)
        sheet.cell(row=sheet.max_row, column=1).alignment = Alignment(wrap_text=True, vertical="top")
        sheet.row_dimensions[sheet.max_row].height = 30 if len(note) > 90 else 16


def peer_columns(runs: list[Run]) -> list[str]:
    names, seen = [], {}
    for run in runs:
        name = f"{run.company.ticker or run.company.name} FY{run.company.financial_year}"
        seen[name] = seen.get(name, 0) + 1
        names.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
    return names


PEER_FIELDS = {"general": ["revenue", "net_profit", "total_assets", "equity", "operating_cash_flow"],
               "bank": ["total_income", "net_profit", "total_assets", "deposits", "advances_net", "equity"]}


def peer_rows(runs: list[Run]) -> list[dict]:
    """Key verified figures (PKR million) and every ratio, one column per run. All runs must share a company type."""
    if not runs or len({r.company.sector for r in runs}) != 1:
        raise ValueError("Compare runs of one company type: banks with banks, non-financial companies with each other.")
    columns = peer_columns(runs)
    values = [verified_values(run) for run in runs]
    metrics = [{m.name: m for m in calculate(run)} for run in runs]  # current definitions for every run
    rows = []
    for key in PEER_FIELDS[runs[0].company.sector]:
        row = {"Metric": f"{LABELS[key]} (PKR m)", "_format": "million"}
        row.update({col: (v[key] / Decimal(10) ** 6 if key in v else None) for col, v in zip(columns, values)})
        rows.append(row)
    for name, first in metrics[0].items():
        row = {"Metric": first.label, "_format": first.format}
        row.update({col: m[name].value if name in m else None for col, m in zip(columns, metrics)})
        rows.append(row)
    return rows


def display_peer(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        shown = {"Metric": row["Metric"]}
        for col, value in row.items():
            if col in ("Metric", "_format"):
                continue
            if value is None:
                shown[col] = "N/A"
            elif row["_format"] == "million":
                shown[col] = f"{value:,.0f}"
            else:
                shown[col] = display_metric(Metric(name="", label="", value=value, format=row["_format"], formula="", inputs=[]))
        out.append(shown)
    return out


def peer_workbook(runs: list[Run]) -> bytes:
    rows = peer_rows(runs)
    columns = peer_columns(runs)
    book = Workbook()
    sheet = book.active
    sheet.title = "Peer comparison"
    header(sheet, ["Metric", *columns], [46] + [20] * len(columns))
    for row in rows:
        sheet.append([row["Metric"], *(as_number(row[c]) for c in columns)])
        fmt = "#,##0" if row["_format"] == "million" else FORMATS[row["_format"]]
        for cell in sheet[sheet.max_row][1:]:
            cell.number_format = fmt
    sheet.append([])
    bases = "; ".join(f"{col}: {r.company.statement_basis}, {r.filename}" for col, r in zip(columns, runs))
    sheet.append(["Notes", "Each column uses that company's own verified values and financial year. Years and statement "
                  "bases may differ, so compare with care. Not investment advice. " + bases])
    output = BytesIO()
    book.save(output)
    return output.getvalue()
