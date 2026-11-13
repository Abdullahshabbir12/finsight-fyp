"""The Model tab: the analyst's assumptions, a five-year forecast, scenarios and a value range."""
from decimal import Decimal
import altair as alt
import pandas as pd
import streamlit as st
from pydantic import ValidationError
from src.calculations.model import (CASH_INPUTS, FORECAST_INPUTS, LIMITATIONS, NOT_ADVICE, VALUE_INPUTS, Model, basis,
                                    build, cases, defaults, pc, unavailable)
from src.market.commodities import guess_sector, sector_context, year_end_month
from src.models import ModelAssumptions, Run
from src.ui.brand import GREEN_100, GREEN_500, GREEN_700, RUST, STONE
from src.validation.review import verified_values

MILLION = Decimal(10) ** 6
HUNDRED = Decimal(100)
INPUT_LABELS = {
    "sales_growth": "Sales growth a year (%)",
    "gross_margin": "Gross margin (%)",
    "operating_costs": "Operating costs, net of other income (% of sales)",
    "finance_cost": "Finance cost a year (PKR m)",
    "tax_rate": "Tax rate (%)",
    "capex": "Capital spending (% of sales)",
    "depreciation": "Last year's depreciation and amortisation (PKR m)",
    "working_capital": "Receivables + inventory (% of sales)",
    "discount_rate": "Discount rate (%)",
    "terminal_growth": "Long-term growth after year 5 (%)",
    "net_debt": "Net debt (PKR m, negative for net cash)",
}
SCENARIO_LABELS = {
    "downside_growth": "Downside: change to sales growth (points)",
    "downside_margin": "Downside: change to gross margin (points)",
    "upside_growth": "Upside: change to sales growth (points)",
    "upside_margin": "Upside: change to gross margin (points)",
    "shock_share": "Share of cost of sales exposed to one commodity (%)",
    "shock_change": "That commodity's price change (%)",
}
CASE_COLOURS = {"Downside": RUST, "Base": GREEN_700, "Upside": GREEN_500, "Base + input-cost shock": STONE}


def key(run: Run, name: str) -> str:
    return f"model_{run.id}_{name}"


def reset(run: Run) -> None:
    """Button callback: forget the analyst's edits so every input shows the report figures again."""
    run.model_assumptions = None
    for name in [*INPUT_LABELS, *SCENARIO_LABELS, "in_report"]:
        st.session_state.pop(key(run, name), None)


def shown(name: str, value: Decimal | None, revenue: Decimal) -> float | None:
    """An assumption as the analyst types it: percent, PKR million, or depreciation in PKR million."""
    if value is None:
        return None
    if name in ("finance_cost", "net_debt"):
        return float(value / MILLION)
    if name == "depreciation":
        return float(value * revenue / MILLION)
    return float(value * HUNDRED)


def stored(name: str, typed: float | None, revenue: Decimal) -> Decimal | None:
    if typed is None:
        return None
    number = Decimal(str(typed))
    if name in ("finance_cost", "net_debt"):
        return number * MILLION
    if name == "depreciation":
        return number * MILLION / revenue
    return number / HUNDRED


def assumption_inputs(run: Run, a: ModelAssumptions, revenue: Decimal) -> dict:
    notes = basis(run)
    typed = {}
    with st.container(border=True):
        top, button = st.columns([4, 1], vertical_alignment="center")
        top.markdown(f"**Your assumptions** · pre-filled from the verified FY{run.company.financial_year} figures; hover "
                     "ⓘ to see where each came from")
        button.button(":material/restart_alt: Reset", on_click=reset, args=(run,), key=key(run, "reset"), width="stretch",
                      help="Put every assumption back to the figures from the report.")
        groups = [("Profit", FORECAST_INPUTS), ("Cash", CASH_INPUTS), ("Value", VALUE_INPUTS)]
        for column, (title, names) in zip(st.columns(3), groups):
            column.caption(title.upper())
            for name in names:
                amount = name in ("finance_cost", "net_debt", "depreciation")
                typed[name] = column.number_input(
                    INPUT_LABELS[name], value=shown(name, getattr(a, name), revenue), step=100.0 if amount else 0.5,
                    format="%.1f" if amount else "%.2f", key=key(run, name), help=notes[name],
                    placeholder="Type it")
    with st.expander("Scenarios and input-cost shock"):
        st.caption("Downside and upside shift the base case's sales growth and gross margin by these points. The shock "
                   "raises (or lowers) the cost of the exposed share of cost of sales, e.g. coal for cement or gas for "
                   "fertiliser.")
        hint = commodity_hint(run)
        if hint:
            st.caption(hint)
        columns = st.columns(3)
        for i, name in enumerate(SCENARIO_LABELS):
            typed[name] = columns[i % 3].number_input(SCENARIO_LABELS[name], value=float(getattr(a, name) * HUNDRED),
                                                      step=0.5, format="%.2f", key=key(run, name))
    typed["in_report"] = st.checkbox("Add this model to the downloaded report (Markdown and PDF)", value=a.in_report,
                                     key=key(run, "in_report"))
    return typed


def commodity_hint(run: Run) -> str:
    sector = guess_sector(run.company.industry)
    if not sector:
        return ""
    year = run.company.financial_year
    context = sector_context(sector, year, year_end_month(run) or 6)
    moves = [f"{item.series} {item.change:+.1%}" for item in context if item.change is not None]
    return (f"For context, World Bank prices linked to {sector.lower()} over FY{year} against the year before: "
            + ", ".join(moves) + ". In US dollars; local costs also move with the rupee. See the Commodities tab for "
            "which are inputs and which are products.") if moves else ""


def assumptions_from(typed: dict, revenue: Decimal) -> ModelAssumptions:
    values = {name: stored(name, typed[name], revenue) for name in INPUT_LABELS}
    values.update({name: Decimal(str(typed[name] or 0)) / HUNDRED for name in SCENARIO_LABELS})
    return ModelAssumptions(**values, in_report=typed["in_report"])


def money(value: Decimal | None) -> str:
    return "" if value is None else f"{value / MILLION:,.1f}"


def forecast_table(model: Model) -> pd.DataFrame:
    base, years = model.base, model.cases["Base"]
    rows = [("Sales", "revenue", "revenue"), ("Gross profit", "gross_profit", "gross_profit"),
            ("Operating costs, net of other income", None, "operating_costs"), ("EBIT", "ebit", "ebit"),
            ("Finance cost", "finance_cost", "finance_cost"), ("Profit before tax", "profit_before_tax", "profit_before_tax"),
            ("Tax", "tax", "tax"), ("Net profit", "net_profit", "net_profit"), ("EPS (PKR)", "eps", "eps"),
            ("Depreciation and amortisation", None, "depreciation"), ("Capital spending", "capex", "capex"),
            ("Increase in working capital", None, "working_capital_change"), ("Free cash flow to the firm", None, "free_cash_flow")]
    table = []
    for label, base_key, year_key in rows:
        if year_key in ("depreciation", "working_capital_change", "free_cash_flow") and years[0].free_cash_flow is None:
            continue
        eps = year_key == "eps"
        fmt = (lambda x: "" if x is None else f"{x:,.2f}") if eps else money
        row = {"Line": label, f"FY{model.base_year} (verified)": fmt(base.get(base_key)) if base_key else ""}
        if label.startswith("Operating costs") and None not in (base.get("gross_profit"), base.get("ebit")):
            row[f"FY{model.base_year} (verified)"] = money(base["gross_profit"] - base["ebit"])
        row.update({f"FY{y.year}": fmt(getattr(y, year_key)) for y in years})
        table.append(row)
    return pd.DataFrame(table)


def scenario_table(model: Model) -> pd.DataFrame:
    a, rows = model.assumptions, []
    for name, (growth_shift, margin_shift, shock) in cases(a).items():
        years = model.cases.get(name)
        if not years:
            continue
        margin = a.gross_margin + margin_shift
        if shock:
            margin -= (1 - margin) * a.shock_share * a.shock_change
        valuation = model.values.get(name)
        rows.append({"Case": name, "Sales growth": pc(a.sales_growth + growth_shift), "Gross margin": pc(margin),
                     f"EPS FY{years[0].year}": f"{years[0].eps:,.2f}", f"EPS FY{years[-1].year}": f"{years[-1].eps:,.2f}",
                     "Value per share (PKR)": (f"{valuation.per_share:,.2f}" if valuation and valuation.per_share is not None
                                               else (valuation.reason if valuation else "Fill in the cash and value inputs"))})
    return pd.DataFrame(rows)


def eps_chart(model: Model) -> None:
    base_eps = model.base.get("eps")
    points = []
    for name, years in model.cases.items():
        if base_eps is not None:
            points.append({"Case": name, "Year": str(model.base_year), "EPS": float(base_eps)})
        points += [{"Case": name, "Year": str(y.year), "EPS": float(y.eps)} for y in years]
    names = list(model.cases)
    colours = alt.Scale(domain=names, range=[CASE_COLOURS[n] for n in names])
    chart = alt.Chart(pd.DataFrame(points)).mark_line(point=True).encode(
        x=alt.X("Year:O", title=None, axis=alt.Axis(labelAngle=0)), y=alt.Y("EPS:Q", title="EPS (PKR)"),
        color=alt.Color("Case:N", scale=colours, sort=names, legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["Case", "Year", alt.Tooltip("EPS:Q", format=",.2f")])
    st.altair_chart(chart.properties(height=260), width="stretch")


def grid_table(model: Model) -> pd.DataFrame:
    rows = []
    for rate, row in model.grid:
        rows.append({"Discount rate": pc(rate), **{f"Growth {pc(g)}": ("" if x is None else f"{x:,.2f}") for g, x in row}})
    return pd.DataFrame(rows)


def value_panel(model: Model) -> None:
    a, base = model.assumptions, model.values.get("Base")
    st.markdown("#### Value per share")
    if model.value_range is None:
        st.warning(base.reason if base and base.reason else "No value under these assumptions.")
        return
    low, high = model.value_range
    rates, growths = [r for r, _ in model.grid], [g for g, _ in model.grid[0][1]]
    left, right = st.columns([1, 2], vertical_alignment="center")
    left.metric("Value range, base case", f"PKR {low:,.0f} – {high:,.0f}")
    right.caption(f"Discount rate {pc(min(rates))} to {pc(max(rates))} and long-term growth {pc(min(growths))} to "
                  f"{pc(max(growths))}, around your {pc(a.discount_rate)} and {pc(a.terminal_growth)}. " + NOT_ADVICE)
    table = grid_table(model).set_index("Discount rate")
    centre = (pc(a.discount_rate), f"Growth {pc(a.terminal_growth)}")
    st.table(table.style.apply(lambda col: [f"background-color: {GREEN_100}; font-weight: 600"
                                            if (i, col.name) == centre else "" for i in col.index]))
    st.caption("Shaded: your discount rate and long-term growth (the base case).")
    with st.expander("How the value is built (base case)"):
        if base and base.enterprise_value is not None:
            lines = [("Present value of free cash flow, years 1-5", money(base.present_value_years)),
                     ("Terminal value at year 5", money(base.terminal_value)),
                     ("Present value of the terminal value", money(base.present_value_terminal)),
                     ("Enterprise value", money(base.enterprise_value)), ("Less net debt", money(a.net_debt)),
                     ("Equity value", money(base.equity_value)), ("Shares", f"{model.shares:,.0f}"),
                     ("Value per share (PKR)", "" if base.per_share is None else f"{base.per_share:,.2f}"),
                     ("Share of value after year 5", "" if base.terminal_share is None else f"{base.terminal_share:.0%}")]
            st.table(pd.DataFrame([{"Step": s, "PKR m": v} for s, v in lines]).set_index("Step"))
        st.caption("Terminal value = year-5 free cash flow × (1 + long-term growth) / (discount rate - long-term growth). "
                   "Value per share = (present values - net debt) / shares.")


def model_panel(run: Run) -> None:
    st.caption("Your assumptions, BrokerLens's arithmetic. The starting year is your verified figures; every assumption "
               "can be changed. " + NOT_ADVICE)
    reason = unavailable(run)
    if reason:
        st.info(reason)
        return
    revenue = verified_values(run)["revenue"]
    typed = assumption_inputs(run, run.model_assumptions or defaults(run), revenue)
    try:
        run.model_assumptions = assumptions_from(typed, revenue)
    except ValidationError:
        st.error("An assumption is out of range (for example a tax rate of 100% or more, or a negative capital "
                 "spending share). Correct it to update the model.")
        return
    model = build(run)
    for check in model.checks:
        st.warning(check)
    if not model.cases:
        st.info("Fill in " + ", ".join(m.lower() for m in model.missing) + " to see the forecast.")
        return
    st.markdown("#### Five-year forecast (base case, PKR million)")
    st.table(forecast_table(model).set_index("Line"))
    st.markdown("#### Cases")
    st.table(scenario_table(model).set_index("Case"))
    eps_chart(model)
    if model.missing:
        cash_ready = all(getattr(model.assumptions, k) is not None for k in CASH_INPUTS)
        st.info("Fill in " + ", ".join(m.lower() for m in model.missing) + " to see "
                + ("the value range." if cash_ready else "free cash flow and the value range."))
    else:
        value_panel(model)
    with st.expander("Limits of this model"):
        st.markdown("\n".join("- " + line for line in LIMITATIONS))
    st.caption("The Excel download at the bottom of the page includes this model as live formulas (Model sheet), so you "
               "can keep working on it in Excel.")
