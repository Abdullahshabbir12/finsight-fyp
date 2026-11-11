"""Chart data built only from verified values. Calculated bridging steps are labelled as calculated."""
from decimal import Decimal
from src.catalog import LABELS
from src.models import Run
from src.validation.review import verified_values

YEAR_FIELDS = {"general": ["revenue", "net_profit", "operating_cash_flow", "total_assets", "equity", "trade_receivables"],
               "bank": ["net_interest_income", "net_profit", "total_assets", "advances_net", "deposits", "equity"]}
# Profit and loss bridge: (field, sign). A sign of 0 marks a printed subtotal.
BRIDGE = {"general": [("revenue", 0), ("cost_of_sales", -1), ("gross_profit", 0), ("operating_profit", 0),
                      ("finance_cost", -1), ("profit_before_tax", 0), ("tax_expense", -1), ("net_profit", 0)],
          "bank": [("interest_earned", 0), ("interest_expensed", -1), ("net_interest_income", 0), ("non_interest_income", 1),
                   ("total_income", 0), ("operating_expenses", -1), ("profit_before_provisions", 0), ("provisions", -1),
                   ("profit_before_tax", 0), ("tax_expense", -1), ("net_profit", 0)]}
OTHER = "Other items (calculated)"


def scale(amounts: list[Decimal]) -> tuple[Decimal, str]:
    largest = max((abs(a) for a in amounts), default=Decimal(0))
    return (Decimal(10) ** 9, "PKR bn") if largest >= 10 ** 10 else (Decimal(10) ** 6, "PKR m")


def year_pairs(run: Run) -> tuple[list[dict], str]:
    """Key figures for the reporting year and the year before, where both are verified."""
    values = verified_values(run)
    year = run.company.financial_year
    keys = [k for k in YEAR_FIELDS[run.company.sector] if k in values and k + "_prior_year" in values]
    divisor, unit = scale([values[k] for k in keys] + [values[k + "_prior_year"] for k in keys])
    rows = []
    for key in keys:
        rows.append({"Figure": LABELS[key], "Year": str(year - 1), "Amount": float(values[key + "_prior_year"] / divisor)})
        rows.append({"Figure": LABELS[key], "Year": str(year), "Amount": float(values[key] / divisor)})
    return rows, unit


def profit_bridge(run: Run) -> tuple[list[dict], str]:
    """From the top line to net profit. Printed subtotals are bars from zero; each step floats between them.

    When the printed lines between two subtotals do not add up (e.g. distribution costs are not extracted), the gap is
    shown as one calculated step, so the chart always matches the printed subtotals.
    """
    values = verified_values(run)
    steps = [(k, s) for k, s in BRIDGE[run.company.sector] if k in values]
    if sum(1 for _, s in steps if s == 0) < 2:
        return [], ""
    divisor, unit = scale([values[k] for k, _ in steps])
    rows, level, pending = [], None, Decimal(0)
    for key, sign in steps:
        if sign == 0:
            if level is not None and values[key] != level + pending:
                gap = values[key] - (level + pending)
                rows.append(step(OTHER, level + pending, gap, divisor, "calculated"))
            level, pending = values[key], Decimal(0)
            rows.append({"Step": LABELS[key], "Start": 0.0, "End": float(level / divisor), "Kind": "subtotal"})
        elif level is not None:
            change = sign * values[key]
            rows.append(step(LABELS[key], level + pending, change, divisor, "increase" if change >= 0 else "decrease"))
            pending += change
    return rows, unit


def step(label: str, start: Decimal, change: Decimal, divisor: Decimal, kind: str) -> dict:
    return {"Step": label, "Start": float(start / divisor), "End": float((start + change) / divisor), "Kind": kind}
