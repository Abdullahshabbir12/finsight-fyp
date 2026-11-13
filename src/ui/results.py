"""Verified values, reproducible metrics and clearly labeled interpretation."""
import calendar
import json
import sqlite3
from decimal import Decimal
from datetime import datetime, timezone
from time import perf_counter
import altair as alt
import pandas as pd
import streamlit as st
from reportlab.platypus import LayoutError
from src.ai.client import AIClient, AIError
from src.ai.council import ROLES, reference_registry, render_text, run_council
from src.ai.synthesis import run_synthesis
from src.calculations.ratios import calculate, display_metric, market_metrics
from src.catalog import LABELS, internal_unit
from src.models import Claim, Run
from src.market.commodities import (SECTORS, WHY, guess_sector, latest_month, sector_context, source_note, window,
                                    year_end_month)
from src.reporting.charts import profit_bridge, year_pairs
from src.ui.brand import GREEN_500, GREEN_700, RUST, STONE
from src.reporting.excel import display_peer, peer_columns, peer_rows, peer_workbook, run_workbook
from src.reporting.export import markdown_report, pdf_report
from src.ui.layout import STEPS, next_button, page_header
from src.ui.model import model_panel
from src.ui.workflow import attach_pdf, show_source, source_viewer
from src.database.store import list_runs, load_run
from src.utils.evaluation import OUTCOMES, aggregate, evaluation, field_outcomes
from src.validation.accounting import STATUS_LABEL, by_priority, current_decision, decide, extraction_notes, findings
from src.validation.review import verified_values


def show_claim(claim: Claim, registry: dict) -> None:
    # Values inside the sentence are inserted by Python from the verified registry, not typed by the AI.
    st.markdown(f"**{claim.kind}** · {render_text(claim.text, registry)}")
    for ref in claim.references:
        item = registry[ref]
        st.caption(f"{ref} · {item['display']}")


def show_analyst(run: Run, role: str, registry: dict) -> None:
    result = run.analysts.get(role)
    if not result:
        st.info("This perspective is not available yet. Run or retry the council above.")
        return
    st.subheader(role)
    show_claim(result.overall_observation, registry)
    for label, claims in [("Positive factors", result.positive_factors), ("Risk factors", result.risk_factors), ("Limitations", result.limitations)]:
        st.markdown("#### " + label)
        if not claims:
            st.caption("None identified in this output.")
        for claim in claims:
            show_claim(claim, registry)
    with st.expander("Referenced metrics and evidence"):
        for ref in dict.fromkeys([*result.key_metrics, *result.evidence]):
            st.write(registry[ref]["display"])


def pct(value) -> str:
    return f"{value:.1%}" if value is not None else "N/A"


def evaluation_screen(run: Run, header: bool = True) -> None:
    stats = evaluation(run)
    if header:
        page_header("Measure the AI", [
            "See how often the AI's numbers matched your verified values, field by field.",
            "Save each finished run (sidebar) to add it to **All saved live runs** at the bottom, for your FYP results.",
            "These are agreement measures against the human review, not audited accuracy.",
        ])
    a, b, c, d = st.columns(4)
    a.metric("Proposal precision", pct(stats["proposal_precision"]), help="Of the numbers the AI proposed, the share that matched the final verified value (sign and flags aside).")
    b.metric("Field recall", pct(stats["field_recall"]), help="Of the fields with a verified value, the share where the AI proposed the right number.")
    c.metric("Strict accuracy", pct(stats["extraction_accuracy"]), help="Fields accepted with no change at all / fields with a verified value. Counts flags, sign fixes and human-filled fields as errors.")
    d.metric("Unavailable", stats["unavailable_fields"])
    st.markdown("#### What happened to each field")
    st.dataframe(pd.DataFrame([{"Outcome": OUTCOMES[k], "Fields": stats["outcome_" + k]} for k in OUTCOMES if stats["outcome_" + k]]),
                 hide_index=True, width="stretch")
    outcomes = field_outcomes(run)
    with st.expander("Per-field outcomes"):
        st.dataframe(pd.DataFrame(outcomes), hide_index=True, width="stretch")
    st.caption("Observed workflow time includes active-session human review. Processing time sums measured PDF and API stages, including failed attempts. Demo results and timings are illustrative and must be excluded from live extraction evaluation.")
    with st.expander("All measures"):
        st.dataframe(pd.DataFrame([{"Measure": k, "Value": "N/A" if v is None else str(v)} for k, v in stats.items()]), hide_index=True, width="stretch")
    x, y = st.columns(2)
    x.download_button("Download evaluation JSON", json.dumps(stats, indent=2), file_name=f"brokerlens-{run.id}-evaluation.json", mime="application/json")
    y.download_button("Download per-field CSV", pd.DataFrame(outcomes).to_csv(index=False), file_name=f"brokerlens-{run.id}-fields.csv", mime="text/csv")
    if run.usage:
        with st.expander("API calls"):
            st.dataframe(pd.DataFrame(run.usage), hide_index=True, width="stretch")
    st.markdown("#### All saved live runs")
    st.caption("Combines every reviewed, non-demo run saved with 'Save run locally'. Use this table for your FYP results across several annual reports.")
    try:
        runs = [load_run(row[0]) for row in list_runs() if not row[3]]
    except (OSError, sqlite3.Error, ValueError):
        st.warning("Saved runs are unavailable. Check the database path and file permissions.")
        return
    summaries, per_field = aggregate(runs)
    if not summaries:
        st.info("No reviewed live runs saved yet. Save this run after verification to include it.")
        return
    st.dataframe(pd.DataFrame(summaries), hide_index=True, width="stretch")
    st.dataframe(pd.DataFrame(per_field), hide_index=True, width="stretch")
    x, y = st.columns(2)
    x.download_button("Download runs CSV", pd.DataFrame(summaries).to_csv(index=False), file_name="brokerlens-all-runs.csv", mime="text/csv")
    y.download_button("Download per-field totals CSV", pd.DataFrame(per_field).to_csv(index=False), file_name="brokerlens-field-totals.csv", mime="text/csv")


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


PRIORITY_ICON = {"high": "🔴", "medium": "🟠", "low": "⚪"}
DECISIONS = ["confirmed", "investigating", "dismissed"]


def findings_panel(run: Run) -> None:
    """Every check result as a card an analyst can open, trace to the PDF and decide on."""
    cards = by_priority(findings(run))
    with st.container(border=True):
        if not cards:
            st.markdown("**✅ No findings from BrokerLens's checks**")
            st.caption("The checks are limited reconciliations and teaching heuristics, not an audit.")
            return
        decided = sum(1 for c in cards if current_decision(run, c)[0])
        high = sum(1 for c in cards if c.priority == "high")
        st.markdown(f"**🚩 {len(cards)} finding{'s' if len(cards) != 1 else ''} to review** · {high} high priority · "
                    f"{decided} of {len(cards)} decided")
        st.caption("Open a finding for the figures behind it, the arithmetic, why it matters and what to check next. "
                   "Findings are prompts for review, not conclusions.")
        for card in cards:
            finding_card(run, card)


def finding_card(run: Run, card) -> None:
    decision, changed = current_decision(run, card)
    status = STATUS_LABEL[decision.status if decision else "open"]
    label = f"{PRIORITY_ICON[card.priority]} **{card.title}** · {card.category} · {status}" + (" · figures changed since" if changed else "")
    with st.expander(label):
        st.write(card.detail)
        if card.calculation:
            st.code(card.calculation, language=None, wrap_lines=True)
        if card.why:
            st.markdown("**Why it matters:** " + card.why)
        if card.next_steps:
            st.markdown("**What to check next**\n" + "\n".join("- " + step for step in card.next_steps))
        if card.fields:
            figure = st.pills("See a figure on its PDF page", card.fields, format_func=LABELS.get, key=f"fig_{run.id}_{card.key}")
            if figure:
                show_source(run, figure, f"finding_source_{run.id}_{card.key}")
        st.markdown("**Your decision**")
        history = run.finding_decisions.get(card.key, [])
        for past in history:
            st.caption(f"{past.at[:16].replace('T', ' ')} · {STATUS_LABEL[past.status]}" + (f" · {past.comment}" if past.comment else ""))
        if changed:
            st.warning("The figures behind this finding changed after your last decision. Review it again.")
        a, b = st.columns([1, 2])
        choice = a.radio("Status", DECISIONS, format_func=STATUS_LABEL.get, key=f"status_{run.id}_{card.key}",
                         index=DECISIONS.index(decision.status) if decision else None)
        comment = b.text_area("Comment (required to dismiss)", key=f"comment_{run.id}_{card.key}", height=96,
                              placeholder="e.g. gap is share of associates, printed on page 439")
        if st.button("Save decision", key=f"decide_{run.id}_{card.key}"):
            if choice is None:
                st.error("Choose a status first.")
                return
            try:
                decide(run, card, choice, comment, datetime.now(timezone.utc).isoformat())
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.toast("Decision recorded. Use Save at the top to keep it.")
                st.rerun()


TEAL = GREEN_700
BRIDGE_COLOURS = alt.Scale(domain=["subtotal", "increase", "decrease", "calculated"],
                           range=[GREEN_700, GREEN_500, RUST, STONE])


def charts_panel(run: Run) -> None:
    st.caption("Drawn only from verified values. Hover a bar for the exact amount.")
    rows, unit = profit_bridge(run)
    if rows:
        st.markdown("#### From top line to net profit")
        frame = pd.DataFrame(rows)
        order = list(dict.fromkeys(frame["Step"]))
        frame["Amount"] = frame["End"] - frame["Start"]
        chart = alt.Chart(frame).mark_bar().encode(
            y=alt.Y("Step:N", sort=order, title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X("Start:Q", title=unit), x2="End:Q",
            color=alt.Color("Kind:N", scale=BRIDGE_COLOURS, legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["Step", alt.Tooltip("Amount:Q", format=",.2f", title=unit), alt.Tooltip("End:Q", format=",.2f", title="Running total")])
        st.altair_chart(chart, width="stretch")
        if any(r["Kind"] == "calculated" for r in rows):
            st.caption("Grey steps are calculated by Python as the gap between two printed subtotals (lines not extracted, "
                       "such as distribution costs, other income or share of associates).")
    pairs, unit = year_pairs(run)
    if pairs:
        st.markdown("#### This year vs last year")
        frame = pd.DataFrame(pairs)
        chart = alt.Chart(frame).mark_bar().encode(
            y=alt.Y("Figure:N", sort=None, title=None, axis=alt.Axis(labelLimit=260)), yOffset="Year:N",
            x=alt.X("Amount:Q", title=unit),
            color=alt.Color("Year:N", scale=alt.Scale(range=["#b9cfc3", GREEN_700]), legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["Figure", "Year", alt.Tooltip("Amount:Q", format=",.2f", title=unit)])
        st.altair_chart(chart, width="stretch")
    if not rows and not pairs:
        st.info("Not enough verified figures for charts. Verify the profit and loss lines and the prior-year figures.")


NOT_LINKED = "Not commodity-linked"


def commodity_panel(run: Run) -> None:
    """International prices of the inputs or products that move a sector's margins, over the company's financial year."""
    st.caption("External context from the World Bank, monthly averages in US dollars. Not verified by BrokerLens, not "
               "used in the ratios, and never sent to the AI analysts.")
    if run.company.sector == "bank":
        st.info("Commodity prices are not a direct driver for banks; interest rates and credit quality matter more.")
        return
    guess = guess_sector(run.company.industry)
    detected = year_end_month(run)
    a, b = st.columns(2)
    options = [NOT_LINKED, *SECTORS]
    sector = a.selectbox("Sector", options, index=options.index(guess) if guess else 0, key="commodity_sector_" + run.id,
                         help="Guessed from the industry you entered; change it if needed.")
    month = b.selectbox("Financial year ends in", list(range(1, 13)), format_func=lambda m: calendar.month_name[m],
                        index=(detected or 6) - 1, key="commodity_month_" + run.id,
                        help="Read from the statement dates." if detected else "Not found in the statements; choose it.")
    if sector == NOT_LINKED:
        st.caption("Choose a sector to see the commodity prices behind its margins (cement, fertiliser, oil, power, "
                   "textiles, steel, sugar, food, cables).")
        return
    year = run.company.financial_year
    context = sector_context(sector, year, month)
    st.markdown(f"**{sector}:** {WHY[sector]}")
    if not context:
        st.warning(f"The World Bank data runs to {latest_month()}, so the financial year ending "
                   f"{calendar.month_name[month]} {year} is not fully covered.")
        return
    first = window(year, month)[0]
    st.markdown(f"Average over FY{year} ({calendar.month_abbr[int(first[5:])]} {first[:4]} to {calendar.month_abbr[month]} {year}) "
                "against the year before:")
    for col, item in zip(st.columns(len(context)), context):
        col.metric(f"{item.series} · {item.unit}", f"{item.average:,.2f}",
                   delta=f"{item.change:+.1%} vs FY{year - 1}" if item.change is not None else None, delta_color="off")
    values = verified_values(run)
    if all(k in values for k in ("revenue", "net_profit", "revenue_prior_year", "net_profit_prior_year")) and \
            values["revenue"] > 0 and values["revenue_prior_year"] > 0:
        margin, prior = values["net_profit"] / values["revenue"], values["net_profit_prior_year"] / values["revenue_prior_year"]
        line = f"For comparison, the company's verified net profit margin was {margin:.1%} in FY{year} against {prior:.1%} in FY{year - 1}"
        if "gross_profit" in values and values["revenue"]:
            line += f"; gross margin in FY{year} was {values['gross_profit'] / values['revenue']:.1%}"
        st.markdown(line + ".")
    start = pd.Timestamp(first + "-01")
    for item in context:
        frame = pd.DataFrame([{"Month": pd.Timestamp(m + "-01"), "Price": price} for m, price in item.months])
        band = alt.Chart(pd.DataFrame([{"start": start, "end": frame["Month"].max()}])).mark_rect(opacity=0.12, color=TEAL).encode(
            x="start:T", x2="end:T")
        line = alt.Chart(frame).mark_line(point=True, color=TEAL).encode(
            x=alt.X("Month:T", title=None), y=alt.Y("Price:Q", title=item.unit, scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("Month:T", format="%b %Y"), alt.Tooltip("Price:Q", format=",.2f", title=item.unit)])
        st.altair_chart((band + line).properties(title=item.series, height=220), width="stretch")
    st.caption(f"Shaded: FY{year}. Source: {source_note()} Prices are in US dollars; the rupee exchange rate, freight and "
               "local taxes are not included, so local costs moved differently. Context for analysis, not a forecast.")


def peer_chart(rows: list[dict], columns: list[str], key: str) -> None:
    options = [r["Metric"] for r in rows if any(r[c] is not None for c in columns)]
    if not options:
        return
    choice = st.selectbox("Chart a measure", options, key=key)
    row = next(r for r in rows if r["Metric"] == choice)
    percent = row["_format"] == "percent"
    frame = pd.DataFrame([{"Company": c, "Value": float(row[c]) * (100 if percent else 1)} for c in columns if row[c] is not None])
    title = "%" if percent else ("PKR m" if row["_format"] == "million" else "x")
    chart = alt.Chart(frame).mark_bar(color=TEAL).encode(
        y=alt.Y("Company:N", sort="-x", title=None), x=alt.X("Value:Q", title=title),
        tooltip=["Company", alt.Tooltip("Value:Q", format=",.2f", title=title)])
    st.altair_chart(chart, width="stretch")


def market_panel(run: Run) -> None:
    c = run.company
    with st.expander("💹 Valuation multiples · enter today's share price", expanded=c.share_price is not None):
        st.caption("Type the price from PSX or your trading terminal; BrokerLens does not fetch prices (PSX market data "
                   "needs a licence). Multiples appear here, in the reports and in Excel. The AI analysis never sees them.")
        a, b, d = st.columns(3)
        price = a.number_input("Share price (PKR)", min_value=0.0, step=0.01, format="%.2f", key="price_" + run.id,
                               value=float(c.share_price) if c.share_price else None)
        dps = b.number_input("Dividend per share (PKR, optional)", min_value=0.0, step=0.01, format="%.2f", key="dps_" + run.id,
                             value=float(c.dividend_per_share) if c.dividend_per_share is not None else None)
        c.price_date = d.text_input("Price date", value=c.price_date, max_chars=40, key="price_date_" + run.id)
        c.share_price = Decimal(str(price)) if price else None
        c.dividend_per_share = Decimal(str(dps)) if dps is not None else None
        for col, metric in zip(st.columns(4), market_metrics(run)):
            col.metric(metric.label, display_metric(metric), help=metric.formula + (" · " + metric.reason if metric.reason else ""))


def peer_panel(run: Run) -> None:
    st.caption("Compare this analysis with other saved analyses of the same company type, side by side.")
    if run.is_demo:
        st.info("The synthetic demo is fictional, so it is not compared with real companies.")
        return
    try:
        saved = [r for r in list_runs() if not r[3] and r[0] != run.id]
    except (OSError, sqlite3.Error):
        st.warning("Saved runs are unavailable. Check the database path and file permissions.")
        return
    if not saved:
        st.info("Save other analyses (Save, at the top) to compare them here.")
        return
    names = {r[0]: f"{r[1]} · saved {r[2][:10]}" for r in saved}
    chosen = st.multiselect("Compare with", list(names), format_func=names.get, key="peers_" + run.id)
    cache = st.session_state.setdefault("_peer_runs", {})
    runs, skipped = [run], []
    for run_id in chosen:
        if run_id not in cache:
            cache[run_id] = load_run(run_id)
        other = cache[run_id]
        try:
            verified_values(other)
        except ValueError:
            skipped.append(f"{other.company.name} (verification not finished)")
            continue
        if other.company.sector != run.company.sector:
            skipped.append(f"{other.company.name} (different company type)")
            continue
        runs.append(other)
    if skipped:
        st.caption("Not compared: " + "; ".join(skipped))
    rows = peer_rows(runs)
    st.dataframe(pd.DataFrame(display_peer(rows)), hide_index=True, width="stretch")
    if len(runs) > 1:
        peer_chart(rows, peer_columns(runs), "peer_chart_" + run.id)
    st.caption("Each column uses that company's own verified values and financial year. Years and statement bases may "
               "differ, so compare with care. Not investment advice.")
    st.download_button("Download comparison (Excel)", peer_workbook(runs), file_name="brokerlens-peer-comparison.xlsx", mime=XLSX)


def results_screen(run: Run) -> None:
    page_header("Research workspace", [
        "Ratios are calculated by Python from your verified values only; the AI never does arithmetic.",
        "Click **Run AI council & synthesis** for four analyst views and a neutral summary. Every claim cites its source.",
        "Download the report at the bottom. It is decision support, not investment advice.",
    ])
    if not run.verified_at or run.review_draft:
        st.info("Finish verification first: ratios and AI analysis only use values you have checked.")
        next_button("Go to verification →", STEPS[2], "goto_verify_from_results")
        return
    try:
        run.metrics = calculate(run)
        values = verified_values(run)
    except ValueError as exc:
        st.warning(str(exc))
        return
    metrics = {m.name: m for m in run.metrics}
    bank = run.company.sector == "bank"
    top_line, top_label = ("total_income", "Total income · PKR m") if bank else ("revenue", "Revenue · PKR m")
    cols = [*st.columns(3), *st.columns(3)]
    cols[0].metric(top_label, f'{values[top_line] / 1000000:,.2f}' if top_line in values else "N/A")
    cols[1].metric("Net profit · PKR m", f'{values["net_profit"] / 1000000:,.2f}' if "net_profit" in values else "N/A")
    cards = (["return_on_assets", "return_on_equity", "advances_to_deposits", "capital_adequacy"] if bank
             else ["return_on_assets", "return_on_equity", "current_ratio", "debt_to_equity"])
    for col, key in zip(cols[2:], cards):
        col.metric(metrics[key].label, display_metric(metrics[key]))
    growth_keys = (("net_interest_income_growth", "net_profit_growth", "deposits_growth") if bank
                   else ("revenue_growth", "net_profit_growth", "operating_cash_flow_growth"))
    growth = [metrics[k] for k in growth_keys if metrics[k].value is not None]
    if growth:
        for col, metric in zip(st.columns(3), growth):
            col.metric(metric.label, display_metric(metric))
    findings_panel(run)
    market_panel(run)
    st.caption("Verified figures and Python-calculated ratios. Everything under the AI button is interpretation.")
    button_label = "Generate demo council & synthesis" if run.is_demo else "Run AI council & synthesis"
    if st.button(button_label, type="primary", disabled=run.synthesis is not None):
        progress = st.empty()
        try:
            client = None if run.is_demo else AIClient()
            run_council(run, client, lambda role: progress.info(f"Analyzing: {role}..."))
            progress.info("Preparing neutral synthesis...")
            run_synthesis(run, client)
            progress.success("All four perspectives and synthesis are ready. Review the cited evidence.")
        except (AIError, ValueError) as exc:
            progress.error(str(exc))
            st.info("Completed perspectives are preserved. Click the same button to retry the remaining work.")
    if "workflow_start" in st.session_state:
        run.timings["workflow_seconds"] = perf_counter() - st.session_state.workflow_start
    registry = reference_registry(run)
    tab_names = ["Overview", "Charts", "Commodities", "Financial Data", "Ratios", "Model", "Peer comparison", *ROLES,
                 "Final Synthesis", "Sources / Evidence", "Evaluation"]
    tabs = dict(zip(tab_names, st.tabs(tab_names)))
    with tabs["Overview"]:
        st.markdown("### Summary")
        st.write(f"{run.company.name} · FY {run.company.financial_year} · {run.company.statement_basis.title()} statements")
        st.success("Human verification saved. All calculations use only the saved verified values.")
        st.write(f"{len(values)} of {len(run.fields)} fields verified · {sum(m.value is not None for m in run.metrics)} of {len(metrics)} ratios available · {len(run.analysts)} of 4 perspectives complete")
        if run.is_demo:
            st.info("DEMO / SYNTHETIC DATA. Analyst outputs are predefined teaching templates reflecting the saved verified values; no API request is made.")
        else:
            st.info("AI-generated interpretation requires source review. Citations show traceability, not proof that the interpretation is correct.")
        st.markdown("### Extraction notes")
        notes = extraction_notes(run)
        for note in notes:
            st.warning(note)
        if not notes:
            st.caption("No extraction issues remain on the verified fields.")
        st.caption("Findings from the accounting checks are at the top of this page. Tolerance: greater of PKR 1 or 1% of "
                   "the larger absolute side. Liquidity, leverage and earnings-quality thresholds are teaching heuristics.")
        if run.company.benchmarks:
            st.markdown("### Supplied benchmark context")
            st.write(run.company.benchmarks)
    with tabs["Charts"]:
        charts_panel(run)
    with tabs["Commodities"]:
        commodity_panel(run)
    with tabs["Financial Data"]:
        reviews = {r.field_name: r for r in run.reviews}
        rows = []
        for f in run.fields:
            r = reviews[f.field_name]
            rows.append({"Field": LABELS[f.field_name], "Extracted raw": f.raw_value or "N/A", "Extracted unit": f.unit,
                "Extracted normalized": str(f.normalized_value) if f.normalized_value is not None else "N/A",
                "Human verified": str(r.verified_value) if r.verified_value is not None else "N/A", "Internal unit": internal_unit(f.field_name),
                "Decision": r.decision, "Year": r.reporting_year, "Source page": r.source_page, "Review note": r.note})
        attach_pdf(run, "attach_data_" + run.id)
        st.caption("👆 Select a row to see that figure highlighted on its PDF page.")
        event = st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", on_select="rerun",
                             selection_mode="single-row", key="data_table_" + run.id)
        picked = event.selection.rows if event else []
        if picked:
            show_source(run, run.fields[picked[0]].field_name, "data_source_" + run.id)
    with tabs["Ratios"]:
        st.caption("Deterministic calculated metrics. The LLM does not calculate these ratios.")
        attach_pdf(run, "attach_ratios_" + run.id)
        st.caption("👆 Select a ratio to see its formula and every input highlighted on its PDF page.")
        event = st.dataframe(pd.DataFrame([{"Metric": m.label, "Result": display_metric(m), "Formula": m.formula,
                                            "Explanation": m.reason} for m in run.metrics]), hide_index=True, width="stretch",
                             on_select="rerun", selection_mode="single-row", key="ratio_table_" + run.id)
        picked = event.selection.rows if event else []
        if picked:
            m = run.metrics[picked[0]]
            st.markdown(f"**{m.label} = {display_metric(m)}**")
            st.code(m.formula, language=None)
            if m.reason:
                st.caption(m.reason)
            for key in m.inputs:
                item = registry.get("field:" + key)
                st.write(item["display"] if item else f"{LABELS[key]}: unavailable")
                if item:
                    show_source(run, key, f"ratio_source_{run.id}_{m.name}")
    with tabs["Model"]:
        model_panel(run)
    with tabs["Peer comparison"]:
        peer_panel(run)
    for role in ROLES:
        with tabs[role]:
            show_analyst(run, role, registry)
    with tabs["Final Synthesis"]:
        if run.synthesis:
            for section in run.synthesis.sections:
                st.markdown("### " + section.heading)
                for claim in section.claims:
                    show_claim(claim, registry)
        else:
            st.info("Generate all four perspectives and synthesis using the button above.")
    with tabs["Sources / Evidence"]:
        st.caption("Physical PDF pages. Corrections may differ from the original quotation; review notes explain the human's final value.")
        for ref, item in registry.items():
            with st.expander(item["display"]):
                st.caption(ref)
                if item.get("source_text"):
                    st.code(item["source_text"], language=None)
                if item.get("review_note"):
                    st.write("Human review note: " + item["review_note"])
                if item.get("inputs"):
                    for key in item["inputs"]:
                        st.write(registry[key]["display"])
        source_viewer(run, "results_sources_" + run.id)
    with tabs["Evaluation"]:
        evaluation_screen(run, header=False)
    with st.container(border=True):
        st.markdown("**Download the research report**")
        st.caption("Verified data, calculations, AI interpretation, sources and limitations. Labelled partial if the AI analysis is incomplete.")
        report = markdown_report(run)
        a, b, x, c = st.columns(4)
        with b:
            try:
                content = pdf_report(run)
                st.download_button("Download PDF", content, file_name=f"brokerlens-{run.id}.pdf", mime="application/pdf", type="primary", width="stretch")
            except (ValueError, OSError, RuntimeError, LayoutError):
                st.warning("PDF export is unavailable. Use Markdown export for this run.")
        a.download_button("Download Markdown", report, file_name=f"brokerlens-{run.id}.md", mime="text/markdown", width="stretch")
        x.download_button("Download Excel", run_workbook(run), file_name=f"brokerlens-{run.id}.xlsx", mime=XLSX, width="stretch",
                          help="Verified data with evidence, ratios as live Excel formulas, valuation from an editable "
                               "price cell, and the financial model with editable assumptions.")
        c.download_button("Download full audit JSON", run.model_dump_json(indent=2), file_name=f"brokerlens-{run.id}-audit.json", mime="application/json", width="stretch")
    next_button("Next: measure the AI →", STEPS[4], "next_from_results")
