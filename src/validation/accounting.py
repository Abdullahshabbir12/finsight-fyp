"""Warnings only. Reconciliation never changes a financial value."""
from decimal import Decimal
from src.catalog import FIELDS, expected_year
from src.models import Run
from src.validation.review import verified_values

NONNEGATIVE = {"revenue", "cost_of_sales", "finance_cost", "total_assets", "current_assets", "inventory",
               "trade_receivables", "cash_equivalents", "total_liabilities", "current_liabilities", "total_debt", "number_of_shares",
               "revenue_prior_year", "total_assets_prior_year", "trade_receivables_prior_year"}
DIVERGENCE_POINTS = Decimal("0.25")  # profit growth exceeding cash-flow growth by 25 percentage points


def reconcile(left: Decimal, right: Decimal) -> tuple[bool, Decimal]:
    """Tolerance: greater of PKR 1 or 1% of the larger absolute side."""
    difference = left - right
    tolerance = max(Decimal(1), max(abs(left), abs(right)) * Decimal("0.01"))
    return abs(difference) <= tolerance, difference


def validate_run(run: Run) -> list[str]:
    values = verified_values(run)
    warnings = []
    for field in run.fields:
        warnings.extend(f"{FIELDS[field.field_name]} extraction: {issue}" for issue in field.issues)
        if field.normalized_value is not None and field.reporting_year != expected_year(field.field_name, run.company.financial_year):
            warnings.append(f"{FIELDS[field.field_name]}: extracted reporting-period mismatch.")
    missing = [FIELDS[k] for k in ("revenue", "net_profit", "total_assets", "total_liabilities", "equity", "operating_cash_flow") if k not in values]
    if missing:
        warnings.append("Missing key verified values: " + ", ".join(missing) + ".")
    for key in NONNEGATIVE & values.keys():
        if values[key] < 0:
            warnings.append(f"{FIELDS[key]} is negative. Confirm sign conventions and source; no automatic change was made.")
    if values.get("equity", Decimal(1)) <= 0:
        warnings.append("Equity is nonpositive; ROE and debt-to-equity are N/A.")
    for keys, left, right, label in [
        (("total_assets", "total_liabilities", "equity"), "total_assets", ("total_liabilities", "equity"), "Assets versus liabilities plus equity"),
        (("gross_profit", "revenue", "cost_of_sales"), "gross_profit", ("revenue", "cost_of_sales"), "Gross profit versus revenue less cost of sales"),
    ]:
        if all(k in values for k in keys):
            expected = values[right[0]] + values[right[1]] if left == "total_assets" else values[right[0]] - values[right[1]]
            ok, difference = reconcile(values[left], expected)
            if not ok:
                warnings.append(f"{label}: difference PKR {difference:,.2f} exceeds the 1% (minimum PKR 1) tolerance. Requires human review.")
    if all(k in values for k in ("net_profit", "operating_cash_flow")) and values["net_profit"] > values["operating_cash_flow"]:
        warnings.append("Net profit exceeds operating cash flow. Cash conversion is an indicator requiring further review; this is not evidence of misconduct.")
    if all(k in values for k in ("current_assets", "current_liabilities")) and values["current_assets"] < values["current_liabilities"]:
        warnings.append("Current assets are below current liabilities. Potential liquidity warning indicator; consider the operating cycle and industry.")
    if all(k in values for k in ("total_debt", "equity")) and values["total_debt"] > values["equity"]:
        warnings.append("Debt exceeds equity. Potential leverage warning indicator; the threshold is a simple teaching heuristic, not an industry benchmark.")
    growth = {k: (values[k] - values[k + "_prior_year"]) / values[k + "_prior_year"]
              for k in ("net_profit", "operating_cash_flow")
              if k in values and values.get(k + "_prior_year", 0) > 0}
    if len(growth) == 2 and growth["net_profit"] - growth["operating_cash_flow"] > DIVERGENCE_POINTS:
        warnings.append("Net profit grew materially faster than operating cash flow year on year. Divergence between profit growth "
                        "and cash flow is an indicator requiring further review; it is not evidence of misconduct.")
    for smaller, larger in [("inventory", "current_assets"), ("current_assets", "total_assets"), ("current_liabilities", "total_liabilities"), ("total_debt", "total_liabilities")]:
        if smaller in values and larger in values and values[smaller] > values[larger]:
            warnings.append(f"{FIELDS[smaller]} exceeds {FIELDS[larger]}. Check units, classification, and statement basis.")
    return warnings
