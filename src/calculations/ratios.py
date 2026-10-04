"""All ratio arithmetic lives here. AI output can never set these results."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from typing import Mapping
from src.catalog import FIELDS
from src.models import Metric, Run
from src.validation.review import verified_values


@dataclass(frozen=True)
class RatioSpec:
    label: str
    numerator: tuple[str, ...]
    denominator: str
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
    spec = SPECS[name]
    inputs = list(spec.numerator) + [spec.denominator]
    numerator_label = " - ".join(FIELDS[k] for k in spec.numerator)
    metric = Metric(name=name, label=spec.label, value=None, format="percent" if spec.percent else "multiple",
                    formula=f"({numerator_label}) / {FIELDS[spec.denominator]}", inputs=inputs)
    if any(values.get(key) is None for key in inputs):
        metric.reason = "Missing verified input: " + ", ".join(FIELDS[k] for k in inputs if values.get(k) is None)
        return metric
    try:
        amounts = {k: Decimal(str(values[k])) for k in inputs}
        if any(not v.is_finite() for v in amounts.values()):
            metric.reason = "Inputs must be finite numbers."
            return metric
        denominator = amounts[spec.denominator]
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


def calculate(run: Run) -> list[Metric]:
    values = verified_values(run)
    if not values:
        raise ValueError("No verified values are available. Review at least one financial field first.")
    return [calculate_ratio(name, values) for name in SPECS]


def display_metric(metric: Metric) -> str:
    if metric.value is None:
        return "N/A"
    return f"{metric.value * 100:,.2f}%" if metric.format == "percent" else f"{metric.value:,.2f}x"
