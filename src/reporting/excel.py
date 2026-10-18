"""Excel workbooks for analysts: verified data with evidence, ratios as live formulas, and peer comparison.

Each ratio is written as an Excel formula over the verified-data cells, beside FinSight's own Python result, so an
analyst can audit the arithmetic or change an input. The price cells start with the user's price (or empty) and can
be edited in Excel; the valuation multiples then recalculate.
"""
from decimal import Decimal
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet
from src.ai.council import reference_registry, render_text
from src.calculations.ratios import ALL_GROWTH, ALL_SPECS, AVERAGE, calculate, display_metric, market_metrics
from src.catalog import LABELS, catalog, internal_unit
from src.models import Metric, Run
from src.validation.accounting import validate_run
from src.validation.review import verified_values

DATA = "Verified data"
HEADER = PatternFill("solid", fgColor="DDEBF7")
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
    sheet.freeze_panes = sheet.cell(row=sheet.max_row + 1, column=1)


def ratio_formula(name: str, ref: dict[str, str]) -> str:
    """The Excel version of a FinSight ratio, built from the same definitions as the Python calculation."""
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
        return f"={ref[numerator]}/(({ref[balance]} + {ref[balance + '_prior_year']})/2)"
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
    rows = [("FinSight analysis", ""), ("Company", c.name), ("Ticker", c.ticker), ("Financial year", c.financial_year),
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
    flags = [w for w in validate_run(run) if " extraction: " not in w]
    summary.append([])
    summary.append(["Flags to review", f"{len(flags)} from FinSight's accounting checks (prompts for review, not findings)"])
    summary.cell(row=summary.max_row, column=1).font = Font(bold=True)
    for flag in flags:
        summary.append(["", flag])
        summary.cell(row=summary.max_row, column=2).alignment = Alignment(wrap_text=True)

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
    header(sheet, ["Metric", "Excel formula result", "FinSight (Python) result", "Definition", "Note / N/A reason"],
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
