"""Warnings only. Reconciliation never changes a financial value."""
from decimal import Decimal
from src.catalog import LABELS, expected_year
from src.models import Run
from src.validation.review import verified_values

NONNEGATIVE = {"revenue", "cost_of_sales", "finance_cost", "total_assets", "current_assets", "inventory",
               "trade_receivables", "cash_equivalents", "total_liabilities", "current_liabilities", "total_debt", "number_of_shares",
               "revenue_prior_year", "total_assets_prior_year", "trade_receivables_prior_year"}
BANK_NONNEGATIVE = {"interest_earned", "interest_expensed", "total_assets", "cash_and_treasury", "lendings", "investments",
                    "advances_net", "deposits", "borrowings", "total_liabilities", "gross_advances", "non_performing_loans",
                    "npl_provisions", "casa_deposits", "operating_expenses", "number_of_shares", "capital_adequacy_ratio",
                    "deposits_prior_year", "advances_net_prior_year", "total_assets_prior_year"}
DIVERGENCE_POINTS = Decimal("0.25")  # profit growth exceeding cash-flow growth by 25 percentage points
# Teaching references, not regulatory advice: SBP's minimum CAR is 10% plus a 1.5% capital conservation buffer.
SBP_MINIMUM_CAR = Decimal("11.5")
HIGH_INFECTION = Decimal("0.10")
# Profit / shares only approximates EPS (non-controlling interest, weighted shares, preference dividends), so the
# check is loose: it catches a share count off by a factor such as 10 or 1,000, not small differences.
EPS_BAND = (Decimal("0.5"), Decimal(2))


def reconcile(left: Decimal, right: Decimal) -> tuple[bool, Decimal]:
    """Tolerance: greater of PKR 1 or 1% of the larger absolute side."""
    difference = left - right
    tolerance = max(Decimal(1), max(abs(left), abs(right)) * Decimal("0.01"))
    return abs(difference) <= tolerance, difference


def validate_run(run: Run) -> list[str]:
    values = verified_values(run)
    warnings = []
    for field in run.fields:
        warnings.extend(f"{LABELS[field.field_name]} extraction: {issue}" for issue in field.issues)
        if field.normalized_value is not None and field.reporting_year != expected_year(field.field_name, run.company.financial_year):
            warnings.append(f"{LABELS[field.field_name]}: extracted reporting-period mismatch.")
    bank = run.company.sector == "bank"
    key_fields = (("net_interest_income", "net_profit", "total_assets", "total_liabilities", "equity", "deposits", "advances_net")
                  if bank else ("revenue", "net_profit", "total_assets", "total_liabilities", "equity", "operating_cash_flow"))
    missing = [LABELS[k] for k in key_fields if k not in values]
    if missing:
        warnings.append("Missing key verified values: " + ", ".join(missing) + ".")
    for key in (BANK_NONNEGATIVE if bank else NONNEGATIVE) & values.keys():
        if values[key] < 0:
            warnings.append(f"{LABELS[key]} is negative. Confirm sign conventions and source; no automatic change was made.")
    if values.get("equity", Decimal(1)) <= 0:
        warnings.append("Equity is nonpositive; ROE and leverage ratios are N/A.")
    if all(k in values for k in ("total_assets", "total_liabilities", "equity")):
        ok, difference = reconcile(values["total_assets"], values["total_liabilities"] + values["equity"])
        if not ok:
            warnings.append(f"Assets versus liabilities plus equity: difference PKR {difference:,.2f} exceeds the 1% (minimum PKR 1) "
                            "tolerance. Requires human review.")
    if values.get("number_of_shares", 0) > 0 and values.get("eps") and "net_profit" in values:
        implied = values["net_profit"] / values["number_of_shares"]
        if not EPS_BAND[0] <= implied / values["eps"] <= EPS_BAND[1]:
            warnings.append(f"Net profit divided by the share count gives PKR {implied:,.2f} per share against reported EPS of PKR "
                            f"{values['eps']:,.2f}. Check the share count (issued shares, not authorised capital or rupee share "
                            "capital) and its unit.")
    return warnings + (bank_checks(values) if bank else company_checks(values))


def identity(values: dict, label: str, total: str, parts: list[tuple[int, str]], note: str = "") -> list[str]:
    """Warn when a printed total differs from the sum of its signed parts by more than the tolerance."""
    if not all(k in values for k in [total, *(k for _, k in parts)]):
        return []
    ok, difference = reconcile(values[total], sum((sign * values[k] for sign, k in parts), Decimal(0)))
    return [] if ok else [f"{label}: difference PKR {difference:,.2f} exceeds the 1% (minimum PKR 1) tolerance. {note}Requires human review."]


def bank_checks(values: dict) -> list[str]:
    warnings = []
    warnings += identity(values, "Net interest income versus interest earned less expensed", "net_interest_income",
                         [(1, "interest_earned"), (-1, "interest_expensed")])
    warnings += identity(values, "Total income versus net interest plus non-interest income", "total_income",
                         [(1, "net_interest_income"), (1, "non_interest_income")])
    warnings += identity(values, "Profit before provisions versus total income less operating expenses", "profit_before_provisions",
                         [(1, "total_income"), (-1, "operating_expenses")], "Share of associates or other items may explain a small gap. ")
    warnings += identity(values, "Profit before tax versus profit before provisions less provisions", "profit_before_tax",
                         [(1, "profit_before_provisions"), (-1, "provisions")], "A levy or a provision sign may explain it. ")
    warnings += identity(values, "Profit after tax versus profit before tax less tax", "net_profit",
                         [(1, "profit_before_tax"), (-1, "tax_expense")])
    for smaller, larger in [("non_performing_loans", "gross_advances"), ("advances_net", "gross_advances"),
                            ("casa_deposits", "deposits"), ("deposits", "total_liabilities"), ("npl_provisions", "non_performing_loans")]:
        if smaller in values and larger in values and values[smaller] > values[larger]:
            warnings.append(f"{LABELS[smaller]} exceeds {LABELS[larger]}. Check units, the note used and the statement basis.")
    if all(k in values for k in ("gross_advances", "advances_net", "npl_provisions")):
        ok, difference = reconcile(values["gross_advances"], values["advances_net"] + values["npl_provisions"])
        if not ok and difference < 0:
            warnings.append("Gross advances are below net advances plus the allowance against non-performing advances. Gross "
                            "advances may omit some financing lines or be a single column; check the advances note.")
    car = values.get("capital_adequacy_ratio")
    if car is not None and not 0 < car < 100:
        warnings.append("Capital adequacy ratio is outside 0-100%. Enter it as a percentage, e.g. 18.25.")
    elif car is not None and car < SBP_MINIMUM_CAR:
        warnings.append(f"Reported capital adequacy is below {SBP_MINIMUM_CAR}%, a teaching reference for SBP's minimum including the "
                        "conservation buffer. Potential capital warning indicator; check current SBP requirements and the bank's disclosures.")
    if values.get("gross_advances") and "non_performing_loans" in values and values["non_performing_loans"] / values["gross_advances"] > HIGH_INFECTION:
        warnings.append("Non-performing loans exceed 10% of gross advances. Potential asset-quality warning indicator (teaching "
                        "heuristic); review provisioning and the classification note.")
    return warnings


def company_checks(values: dict) -> list[str]:
    warnings = []
    for keys, left, right, label in [
        (("gross_profit", "revenue", "cost_of_sales"), "gross_profit", ("revenue", "cost_of_sales"), "Gross profit versus revenue less cost of sales"),
    ]:
        if all(k in values for k in keys):
            expected = values[right[0]] - values[right[1]]
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
            warnings.append(f"{LABELS[smaller]} exceeds {LABELS[larger]}. Check units, classification, and statement basis.")
    return warnings
