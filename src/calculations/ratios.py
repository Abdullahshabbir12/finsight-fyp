"""All ratio arithmetic lives here. AI output can never set these results."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from typing import Mapping
from src.catalog import LABELS
from src.models import Metric, Run
from src.validation.review import verified_values


@dataclass(frozen=True)
class RatioSpec:
    label: str
    numerator: tuple[str, ...]
    denominator: str | tuple[str, ...]  # a tuple is summed, e.g. earning assets
    percent: bool = False
    allow_negative_numerator: bool = True


SPECS = {
    "gross_profit_margin": RatioSpec("Gross Profit Margin", ("gross_profit",), "revenue", True),
    "operating_margin": RatioSpec("Operating Margin", ("operating_profit",), "revenue", True),
    "net_profit_margin": RatioSpec("Net Profit Margin", ("net_profit",), "revenue", True),
    "return_on_assets": RatioSpec("Return on Assets", ("net_profit",), "total_assets", True),
    "return_on_equity": RatioSpec("Return on Equity", ("net_profit",), "equity", True),
    "current_ratio": RatioSpec("Current Ratio", ("current_assets",), "current_liabilities", allow_negative_numerator=False),
    "quick_ratio": RatioSpec("Quick Ratio", ("current_assets", "inventory"), "current_liabilities", allow_negative_numerator=False),
    "debt_to_equity": RatioSpec("Debt to Equity", ("total_debt",), "equity", allow_negative_numerator=False),
    "debt_ratio": RatioSpec("Debt Ratio", ("total_liabilities",), "total_assets", True, False),
    "interest_coverage": RatioSpec("Interest Coverage", ("operating_profit",), "finance_cost"),
    "operating_cash_flow_margin": RatioSpec("Operating Cash Flow Margin", ("operating_cash_flow",), "revenue", True),
    "operating_cash_flow_to_debt": RatioSpec("Operating Cash Flow to Debt", ("operating_cash_flow",), "total_debt"),
    "asset_turnover": RatioSpec("Asset Turnover", ("revenue",), "total_assets", allow_negative_numerator=False),
    "receivables_turnover": RatioSpec("Receivables Turnover", ("revenue",), "trade_receivables", allow_negative_numerator=False),
}


def calculate_ratio(name: str, values: Mapping[str, Decimal | None]) -> Metric:
    spec = ALL_SPECS[name]
    parts = spec.denominator if isinstance(spec.denominator, tuple) else (spec.denominator,)
    inputs = list(spec.numerator) + list(parts)
    # Square brackets keep labels such as "Revenue / Sales" from reading as a second division.
    numerator_label = " - ".join(f"[{LABELS[k]}]" for k in spec.numerator)
    if len(spec.numerator) > 1:
        numerator_label = f"({numerator_label})"
    denominator_label = " + ".join(f"[{LABELS[k]}]" for k in parts)
    if len(parts) > 1:
        denominator_label = f"({denominator_label})"
    metric = Metric(name=name, label=spec.label, value=None, format="percent" if spec.percent else "multiple",
                    formula=f"{numerator_label} / {denominator_label}", inputs=inputs)
    if any(values.get(key) is None for key in inputs):
        metric.reason = "Missing verified input: " + ", ".join(LABELS[k] for k in inputs if values.get(k) is None)
        return metric
    try:
        amounts = {k: Decimal(str(values[k])) for k in inputs}
        if any(not v.is_finite() for v in amounts.values()):
            metric.reason = "Inputs must be finite numbers."
            return metric
        denominator = sum((amounts[k] for k in parts), Decimal(0))
        if denominator <= 0:
            metric.reason = "Denominator is zero or negative; this ratio is not meaningful."
            return metric
        numerator = amounts[spec.numerator[0]]
        if len(spec.numerator) == 2:
            if any(amounts[k] < 0 for k in spec.numerator):
                metric.reason = "Current assets or inventory is negative."
                return metric
            numerator -= amounts[spec.numerator[1]]
        if numerator < 0 and not spec.allow_negative_numerator:
            metric.reason = "Negative numerator requires review before this ratio is meaningful."
            return metric
        with localcontext() as ctx:
            ctx.prec = 28
            metric.value = numerator / denominator
    except (InvalidOperation, ArithmeticError, ValueError):
        metric.reason = "Invalid financial input."
    return metric


# Year-on-year growth: (current - prior) / prior. A zero or negative prior year makes growth meaningless.
GROWTH = {
    "revenue_growth": ("Revenue Growth", "revenue"),
    "net_profit_growth": ("Net Profit Growth", "net_profit"),
    "operating_cash_flow_growth": ("Operating Cash Flow Growth", "operating_cash_flow"),
}
# Returns and turnover on the average of opening and closing balances, the textbook definition.
AVERAGE = {
    "return_on_average_assets": ("Return on Average Assets", "net_profit", "total_assets", True),
    "return_on_average_equity": ("Return on Average Equity", "net_profit", "equity", True),
    "average_receivables_turnover": ("Receivables Turnover (average)", "revenue", "trade_receivables", False),
}


def _amounts(values: Mapping[str, Decimal | None], keys: list[str]) -> dict[str, Decimal] | str:
    missing = [LABELS[k] for k in keys if values.get(k) is None]
    if missing:
        return "Missing verified input: " + ", ".join(missing)
    amounts = {k: Decimal(str(values[k])) for k in keys}
    return amounts if all(v.is_finite() for v in amounts.values()) else "Inputs must be finite numbers."


def calculate_growth(name: str, values: Mapping[str, Decimal | None]) -> Metric:
    label, field = ALL_GROWTH[name]
    prior = field + "_prior_year"
    metric = Metric(name=name, label=label, value=None, format="percent", inputs=[field, prior],
                    formula=f"([{LABELS[field]}] - [{LABELS[prior]}]) / [{LABELS[prior]}]")
    amounts = _amounts(values, [field, prior])
    if isinstance(amounts, str):
        metric.reason = amounts
    elif amounts[prior] <= 0:
        metric.reason = "Prior-year value is zero or negative; a growth rate is not meaningful."
    else:
        with localcontext() as ctx:
            ctx.prec = 28
            metric.value = (amounts[field] - amounts[prior]) / amounts[prior]
    return metric


def calculate_average(name: str, values: Mapping[str, Decimal | None]) -> Metric:
    label, numerator, balance, percent = AVERAGE[name]
    prior = balance + "_prior_year"
    metric = Metric(name=name, label=label, value=None, format="percent" if percent else "multiple",
                    inputs=[numerator, balance, prior],
                    formula=f"[{LABELS[numerator]}] / (([{LABELS[balance]}] + [{LABELS[prior]}]) / 2)")
    amounts = _amounts(values, [numerator, balance, prior])
    if isinstance(amounts, str):
        metric.reason = amounts
        return metric
    average = (amounts[balance] + amounts[prior]) / 2
    if average <= 0:
        metric.reason = "Average balance is zero or negative; this ratio is not meaningful."
    elif not percent and amounts[numerator] < 0:
        metric.reason = "Negative numerator requires review before this ratio is meaningful."
    else:
        with localcontext() as ctx:
            ctx.prec = 28
            metric.value = amounts[numerator] / average
    return metric


# Banks: margins on earning assets, efficiency, funding, asset quality and capital instead of
# gross margin, current ratio and debt ratios, which do not fit a deposit-funded balance sheet.
BANK_SPECS = {
    "net_interest_margin": RatioSpec("Net Interest Margin (year-end earning assets)", ("net_interest_income",),
                                     ("lendings", "investments", "advances_net"), True),
    "cost_to_income": RatioSpec("Cost to Income", ("operating_expenses",), "total_income", True, False),
    "return_on_assets": SPECS["return_on_assets"],
    "return_on_equity": SPECS["return_on_equity"],
    "non_interest_income_share": RatioSpec("Non-Interest Income Share", ("non_interest_income",), "total_income", True),
    "advances_to_deposits": RatioSpec("Advances to Deposits (ADR)", ("advances_net",), "deposits", True, False),
    "investments_to_deposits": RatioSpec("Investments to Deposits", ("investments",), "deposits", True, False),
    "casa_ratio": RatioSpec("Current and Savings Deposits Ratio (CASA)", ("casa_deposits",), "deposits", True, False),
    "infection_ratio": RatioSpec("Non-Performing Loan Ratio (infection)", ("non_performing_loans",), "gross_advances", True, False),
    "coverage_ratio": RatioSpec("Provision Coverage", ("npl_provisions",), "non_performing_loans", True, False),
    "equity_to_assets": RatioSpec("Equity to Assets", ("equity",), "total_assets", True),
}
ALL_SPECS = {**SPECS, **BANK_SPECS}
BANK_GROWTH = {
    "net_interest_income_growth": ("Net Interest Income Growth", "net_interest_income"),
    "net_profit_growth": ("Net Profit Growth", "net_profit"),
    "advances_growth": ("Advances Growth", "advances_net"),
    "deposits_growth": ("Deposits Growth", "deposits"),
}
BANK_AVERAGE = {k: AVERAGE[k] for k in ("return_on_average_assets", "return_on_average_equity")}
ALL_GROWTH = {**GROWTH, **BANK_GROWTH}


def reported_capital_adequacy(values: Mapping[str, Decimal | None]) -> Metric:
    """CAR is calculated by the bank under SBP's Basel III rules; FinSight shows the reported figure."""
    metric = Metric(name="capital_adequacy", label="Capital Adequacy Ratio (reported)", value=None, format="percent",
                    formula="[Capital Adequacy Ratio (reported)], as printed by the bank", inputs=["capital_adequacy_ratio"])
    car = values.get("capital_adequacy_ratio")
    if car is None:
        metric.reason = "Missing verified input: Capital Adequacy Ratio (reported)"
    else:
        metric.value = Decimal(str(car)) / 100
    return metric


def calculate(run: Run) -> list[Metric]:
    values = verified_values(run)
    if not values:
        raise ValueError("No verified values are available. Review at least one financial field first.")
    if run.company.sector == "bank":
        return ([calculate_ratio(name, values) for name in BANK_SPECS] + [reported_capital_adequacy(values)]
                + [calculate_growth(name, values) for name in BANK_GROWTH] + [calculate_average(name, values) for name in BANK_AVERAGE])
    return ([calculate_ratio(name, values) for name in SPECS] + [calculate_growth(name, values) for name in GROWTH]
            + [calculate_average(name, values) for name in AVERAGE])


def display_metric(metric: Metric) -> str:
    if metric.value is None:
        return "N/A"
    return f"{metric.value * 100:,.2f}%" if metric.format == "percent" else f"{metric.value:,.2f}x"
