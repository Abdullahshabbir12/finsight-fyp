"""Financial model: a five-year forecast, free cash flow and a discounted-cash-flow value range.

The analyst owns every assumption. BrokerLens pre-fills them from the verified figures and says where each came from,
does all the arithmetic, and flags assumptions far from the report. The result is a range of values under the
analyst's assumptions: not a target price, not a recommendation, and never sent to the AI analysts.

Definitions (the Excel model uses the same ones):
- EBIT = profit before tax + finance cost, so operating costs (gross profit - EBIT) are net of other income, levies
  and any share of associates.
- Tax applies to positive profit only. NOPAT = EBIT less tax on positive EBIT.
- Free cash flow to the firm = NOPAT + depreciation - capital spending - increase in working capital, where working
  capital is trade receivables + inventory as a share of sales (trade payables are not extracted).
- Terminal value = year-5 free cash flow x (1 + long-term growth) / (discount rate - long-term growth).
- Value per share = (present value of years 1-5 + present value of the terminal value - net debt) / shares.
"""
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from pydantic import ValidationError
from src.catalog import LABELS as FIELD_LABELS
from src.models import ModelAssumptions, Run
from src.validation.review import verified_values

YEARS = 5
PLACEHOLDER_RATE = Decimal("0.18")
PLACEHOLDER_GROWTH = Decimal("0.05")
RATE_STEPS = tuple(Decimal(s) for s in ("-0.02", "-0.01", "0", "0.01", "0.02"))
GROWTH_STEPS = tuple(Decimal(s) for s in ("-0.01", "0", "0.01"))
# Teaching thresholds for the assumption checks, like the accounting checks' thresholds.
GROWTH_GAP, MARGIN_GAP, TAX_GAP, TERMINAL_SHARE = Decimal("0.10"), Decimal("0.05"), Decimal("0.10"), Decimal("0.75")

LABELS = {
    "sales_growth": "Sales growth a year",
    "gross_margin": "Gross margin",
    "operating_costs": "Operating costs, net of other income (% of sales)",
    "finance_cost": "Finance cost a year",
    "tax_rate": "Tax rate",
    "capex": "Capital spending (% of sales)",
    "depreciation": "Depreciation and amortisation (% of sales)",
    "working_capital": "Receivables + inventory (% of sales)",
    "discount_rate": "Discount rate (cost of capital)",
    "terminal_growth": "Long-term growth after year 5",
    "net_debt": "Net debt (borrowings less cash)",
}
AMOUNTS = {"finance_cost", "net_debt"}  # PKR; everything else is a rate
FORECAST_INPUTS = ("sales_growth", "gross_margin", "operating_costs", "finance_cost", "tax_rate")
CASH_INPUTS = ("capex", "depreciation", "working_capital")
VALUE_INPUTS = ("discount_rate", "terminal_growth", "net_debt")
NOT_ADVICE = ("A range of values under your assumptions: not a target price and not a recommendation. "
              "The AI analysts never see this model.")
LIMITATIONS = [
    "One year of history: growth and margins are your assumptions, not a trend.",
    "Operating costs are gross profit less (profit before tax + finance cost), so they include other income, levies "
    "and any share of associates.",
    "Working capital uses trade receivables and inventory only; trade payables are not extracted, so cash tied up "
    "in working capital may be overstated.",
    "Tax applies to positive profit only; tax losses carried forward are ignored.",
    "One growth rate and one margin for all five years; the terminal value assumes steady growth after year 5.",
]


@dataclass(frozen=True)
class Year:
    year: int
    revenue: Decimal
    gross_profit: Decimal
    operating_costs: Decimal
    ebit: Decimal
    finance_cost: Decimal
    profit_before_tax: Decimal
    tax: Decimal
    net_profit: Decimal
    eps: Decimal
    nopat: Decimal
    depreciation: Decimal | None = None
    capex: Decimal | None = None
    working_capital_change: Decimal | None = None
    free_cash_flow: Decimal | None = None


@dataclass(frozen=True)
class Valuation:
    present_value_years: Decimal | None = None
    terminal_value: Decimal | None = None
    present_value_terminal: Decimal | None = None
    enterprise_value: Decimal | None = None
    equity_value: Decimal | None = None
    per_share: Decimal | None = None
    terminal_share: Decimal | None = None
    reason: str = ""


@dataclass
class Model:
    assumptions: ModelAssumptions
    base_year: int
    shares: Decimal
    base: dict[str, Decimal | None]          # the verified year the forecast starts from
    cases: dict[str, list[Year]]             # scenario name -> five forecast years
    values: dict[str, Valuation]
    grid: list[tuple[Decimal, list[tuple[Decimal, Decimal | None]]]]  # discount rate -> (growth, value per share)
    value_range: tuple[Decimal, Decimal] | None
    missing: list[str] = field(default_factory=list)   # assumptions still to fill, as labels
    checks: list[str] = field(default_factory=list)


def unavailable(run: Run) -> str:
    """Why the model cannot be built for this run, or an empty string."""
    if run.company.sector == "bank":
        return ("The model covers non-financial companies. Banks need a different model (loans, deposits and interest "
                "margin), which BrokerLens does not build yet.")
    values = verified_values(run)
    missing = [FIELD_LABELS[k] for k in ("revenue", "number_of_shares") if not values.get(k) or values[k] <= 0]
    return "The model needs a verified, positive " + " and ".join(missing) + "." if missing else ""


def gross_profit(values: dict[str, Decimal]) -> Decimal | None:
    if values.get("gross_profit") is not None:
        return values["gross_profit"]
    if values.get("cost_of_sales") is not None and values.get("revenue") is not None:
        return values["revenue"] - values["cost_of_sales"]
    return None


def valid(**candidates) -> dict:
    """Keep the pre-filled assumptions the model accepts; anything out of range is left for the analyst."""
    kept = {}
    for key, value in candidates.items():
        if value is None:
            continue
        try:
            ModelAssumptions(**{key: value})
        except ValidationError:
            continue
        kept[key] = value
    return kept


def defaults(run: Run) -> ModelAssumptions:
    """Assumptions pre-filled from the verified year; the discount rate and long-term growth are placeholders."""
    v = verified_values(run)
    revenue, prior, gp = v["revenue"], v.get("revenue_prior_year"), gross_profit(v)
    pbt, fc, tax = v.get("profit_before_tax"), v.get("finance_cost"), v.get("tax_expense")
    debt, cash = v.get("total_debt"), v.get("cash_equivalents")
    receivables, inventory, capex = v.get("trade_receivables"), v.get("inventory"), v.get("capital_expenditure")
    with localcontext() as ctx:
        ctx.prec = 28
        return ModelAssumptions(**valid(
            sales_growth=(revenue - prior) / prior if prior and prior > 0 else None,
            gross_margin=gp / revenue if gp is not None else None,
            operating_costs=(gp - pbt - fc) / revenue if None not in (gp, pbt, fc) else None,
            finance_cost=fc,
            tax_rate=tax / pbt if tax is not None and pbt and pbt > 0 else None,
            capex=capex / revenue if capex is not None else None,
            working_capital=(receivables + inventory) / revenue if None not in (receivables, inventory) else None,
            discount_rate=PLACEHOLDER_RATE, terminal_growth=PLACEHOLDER_GROWTH,
            net_debt=debt - (cash or 0) if debt is not None else None))


def page(run: Run, key: str) -> str:
    review = next((r for r in run.reviews if r.field_name == key), None)
    return f"p. {review.source_page}" if review and review.source_page else "no page"


def basis(run: Run) -> dict[str, str]:
    """Where each pre-filled assumption came from, with the PDF pages of its verified inputs."""
    d, y = defaults(run), run.company.financial_year
    v = verified_values(run)

    def said(name: str, text: str) -> str:
        return text if getattr(d, name) is not None else "Not available from the verified figures: type your own."

    gp_page = page(run, "gross_profit") if v.get("gross_profit") is not None else page(run, "cost_of_sales")
    out = {
        "sales_growth": said("sales_growth", f"FY{y} sales growth was {pc(d.sales_growth)} (sales {page(run, 'revenue')}, "
                                             f"prior year {page(run, 'revenue_prior_year')})."),
        "gross_margin": said("gross_margin", f"FY{y} gross profit / sales was {pc(d.gross_margin)} ({gp_page})."),
        "operating_costs": said("operating_costs", f"FY{y} (gross profit - profit before tax - finance cost) / sales was "
                                                   f"{pc(d.operating_costs)} ({page(run, 'profit_before_tax')})."),
        "finance_cost": said("finance_cost", f"FY{y} finance cost was {pkr_m(d.finance_cost)} ({page(run, 'finance_cost')}); "
                                             "held flat. Change it if borrowing will change."),
        "tax_rate": said("tax_rate", f"FY{y} tax / profit before tax was {pc(d.tax_rate)} ({page(run, 'tax_expense')})."),
        "capex": said("capex", f"FY{y} capital expenditure / sales was {pc(d.capex)} ({page(run, 'capital_expenditure')})."),
        "depreciation": "Not extracted by BrokerLens: type last year's depreciation and amortisation from the cash flow "
                        "statement or its notes (your input, no page link).",
        "working_capital": said("working_capital", f"FY{y} (trade receivables + inventory) / sales was "
                                                   f"{pc(d.working_capital)} ({page(run, 'trade_receivables')})."),
        "discount_rate": "BrokerLens placeholder. Use your firm's cost of capital.",
        "terminal_growth": "BrokerLens placeholder. Keep it below the discount rate.",
        "net_debt": (f"FY{y} total debt less cash was {pkr_m(d.net_debt)} ({page(run, 'total_debt')}). Subtract other "
                     "liquid investments if you count them as cash." if d.net_debt is not None else
                     "Total debt was not verified: type borrowings less cash (negative for net cash)."),
    }
    return out


def pc(value: Decimal | None) -> str:
    return "N/A" if value is None else f"{value * 100:,.2f}%"


def pkr_m(value: Decimal | None) -> str:
    return "N/A" if value is None else f"PKR {value / Decimal(10) ** 6:,.1f} m"


def forecast(base_year: int, revenue: Decimal, shares: Decimal, a: ModelAssumptions, growth_shift: Decimal = Decimal(0),
             margin_shift: Decimal = Decimal(0), shock: bool = False) -> list[Year] | None:
    """Five forecast years. Free cash flow only when the cash inputs are set. None when the case is impossible."""
    growth, margin = a.sales_growth + growth_shift, a.gross_margin + margin_shift
    if shock:  # the exposed share of cost of sales moves with the commodity price
        margin -= (1 - margin) * a.shock_share * a.shock_change
    if growth <= -1:
        return None
    cash = all(getattr(a, k) is not None for k in CASH_INPUTS)
    years, previous = [], revenue
    with localcontext() as ctx:
        ctx.prec = 28
        for t in range(1, YEARS + 1):
            sales = previous * (1 + growth)
            gp = sales * margin
            costs = sales * a.operating_costs
            ebit = gp - costs
            pbt = ebit - a.finance_cost
            tax = max(pbt, Decimal(0)) * a.tax_rate
            net = pbt - tax
            nopat = ebit - max(ebit, Decimal(0)) * a.tax_rate
            extra = {}
            if cash:
                dep, capex, change = sales * a.depreciation, sales * a.capex, (sales - previous) * a.working_capital
                extra = {"depreciation": dep, "capex": capex, "working_capital_change": change,
                         "free_cash_flow": nopat + dep - capex - change}
            years.append(Year(base_year + t, sales, gp, costs, ebit, a.finance_cost, pbt, tax, net, net / shares, nopat,
                              **extra))
            previous = sales
    return years


def value(years: list[Year], rate: Decimal, growth: Decimal, net_debt: Decimal, shares: Decimal) -> Valuation:
    if rate <= growth:
        return Valuation(reason="The discount rate must be above long-term growth.")
    if rate <= 0:
        return Valuation(reason="The discount rate must be positive.")
    with localcontext() as ctx:
        ctx.prec = 28
        pv = sum((y.free_cash_flow / (1 + rate) ** t for t, y in enumerate(years, start=1)), Decimal(0))
        terminal = years[-1].free_cash_flow * (1 + growth) / (rate - growth)
        pv_terminal = terminal / (1 + rate) ** len(years)
        enterprise = pv + pv_terminal
        equity = enterprise - net_debt
        share = pv_terminal / enterprise if enterprise > 0 else None
        if equity <= 0:
            return Valuation(pv, terminal, pv_terminal, enterprise, equity, None, share,
                             "Equity value is zero or negative under these assumptions.")
        return Valuation(pv, terminal, pv_terminal, enterprise, equity, equity / shares, share)


def cases(a: ModelAssumptions) -> dict[str, tuple[Decimal, Decimal, bool]]:
    out = {"Downside": (a.downside_growth, a.downside_margin, False), "Base": (Decimal(0), Decimal(0), False),
           "Upside": (a.upside_growth, a.upside_margin, False)}
    if a.shock_share and a.shock_change:
        out["Base + input-cost shock"] = (Decimal(0), Decimal(0), True)
    return out


def build(run: Run, assumptions: ModelAssumptions | None = None) -> Model:
    reason = unavailable(run)
    if reason:
        raise ValueError(reason)
    v = verified_values(run)
    a = assumptions or run.model_assumptions or defaults(run)
    revenue, shares, gp = v["revenue"], v["number_of_shares"], gross_profit(v)
    pbt, fc = v.get("profit_before_tax"), v.get("finance_cost")
    base = {"revenue": revenue, "gross_profit": gp, "ebit": pbt + fc if None not in (pbt, fc) else None,
            "finance_cost": fc, "profit_before_tax": pbt, "tax": v.get("tax_expense"), "net_profit": v.get("net_profit"),
            "eps": v.get("eps"), "capex": v.get("capital_expenditure")}
    model = Model(a, run.company.financial_year, shares, base, {}, {}, [], None)
    model.missing = [LABELS[k] for k in (*FORECAST_INPUTS, *CASH_INPUTS, *VALUE_INPUTS) if getattr(a, k) is None]
    if any(getattr(a, k) is None for k in FORECAST_INPUTS):
        model.checks = assumption_checks(run, model)
        return model
    for name, (growth_shift, margin_shift, shock) in cases(a).items():
        years = forecast(model.base_year, revenue, shares, a, growth_shift, margin_shift, shock)
        if years:
            model.cases[name] = years
    if all(getattr(a, k) is not None for k in (*CASH_INPUTS, *VALUE_INPUTS)):
        for name, years in model.cases.items():
            model.values[name] = value(years, a.discount_rate, a.terminal_growth, a.net_debt, shares)
        base_years = model.cases["Base"]
        for step in RATE_STEPS:
            rate = a.discount_rate + step
            if rate <= 0:
                continue
            row = []
            for g_step in GROWTH_STEPS:
                growth = a.terminal_growth + g_step
                row.append((growth, value(base_years, rate, growth, a.net_debt, shares).per_share))
            model.grid.append((rate, row))
        found = [x for _, row in model.grid for _, x in row if x is not None]
        model.value_range = (min(found), max(found)) if found else None
    model.checks = assumption_checks(run, model)
    return model


def assumption_checks(run: Run, model: Model) -> list[str]:
    """Plain-language flags where the analyst's assumptions are far from the verified year or strain the model."""
    a, d, out = model.assumptions, defaults(run), []
    if a.sales_growth is not None and d.sales_growth is not None and abs(a.sales_growth - d.sales_growth) > GROWTH_GAP:
        out.append(f"Sales growth of {pc(a.sales_growth)} a year is far from last year's {pc(d.sales_growth)}. Over five "
                   f"years it makes sales {(1 + a.sales_growth) ** YEARS:,.2f} times today's.")
    if a.gross_margin is not None and d.gross_margin is not None and abs(a.gross_margin - d.gross_margin) > MARGIN_GAP:
        out.append(f"Gross margin of {pc(a.gross_margin)} differs from last year's {pc(d.gross_margin)} by more than "
                   "5 percentage points.")
    if a.tax_rate is not None and d.tax_rate is not None and abs(a.tax_rate - d.tax_rate) > TAX_GAP:
        out.append(f"Tax rate of {pc(a.tax_rate)} differs from last year's effective rate of {pc(d.tax_rate)} by more "
                   "than 10 percentage points.")
    if a.depreciation is not None and a.capex is not None and a.depreciation > a.capex:
        out.append("Depreciation is above capital spending, so the asset base shrinks every year. Over the long run "
                   "capital spending usually at least matches depreciation.")
    placeholders = [LABELS[k].lower() for k, p in (("discount_rate", PLACEHOLDER_RATE), ("terminal_growth", PLACEHOLDER_GROWTH))
                    if getattr(a, k) == p]
    if placeholders:
        out.append("The " + " and ".join(placeholders) + (" are still BrokerLens placeholders." if len(placeholders) > 1
                   else " is still a BrokerLens placeholder.") + " Replace with your own before using the value range.")
    if a.discount_rate is not None and a.terminal_growth is not None and a.discount_rate <= a.terminal_growth:
        out.append("The discount rate must be above long-term growth; otherwise the terminal value has no meaning.")
    base = model.values.get("Base")
    if base and base.terminal_share is not None and base.terminal_share > TERMINAL_SHARE:
        out.append(f"{base.terminal_share:.0%} of the value comes after year 5, so small changes to long-term growth or "
                   "the discount rate move the value a lot.")
    years = model.cases.get("Base")
    if years and years[-1].free_cash_flow is not None and years[-1].free_cash_flow <= 0:
        out.append("Year-5 free cash flow is zero or negative, so the terminal value is not meaningful.")
    return out
