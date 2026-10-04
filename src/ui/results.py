"""Verified values, reproducible metrics and clearly labeled interpretation."""
import json
import sqlite3
from time import perf_counter
import pandas as pd
import streamlit as st
from reportlab.platypus import LayoutError
from src.ai.client import AIClient, AIError
from src.ai.council import ROLES, reference_registry, render_text, run_council
from src.ai.synthesis import run_synthesis
from src.calculations.ratios import calculate, display_metric
from src.catalog import FIELDS, internal_unit
from src.models import Claim, Run
from src.reporting.export import markdown_report, pdf_report
from src.ui.layout import STEPS, next_button, page_header
from src.ui.workflow import source_viewer
from src.database.store import list_runs, load_run
from src.utils.evaluation import OUTCOMES, aggregate, evaluation, field_outcomes
from src.validation.accounting import validate_run
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
    x.download_button("Download evaluation JSON", json.dumps(stats, indent=2), file_name=f"finsight-{run.id}-evaluation.json", mime="application/json")
    y.download_button("Download per-field CSV", pd.DataFrame(outcomes).to_csv(index=False), file_name=f"finsight-{run.id}-fields.csv", mime="text/csv")
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
    x.download_button("Download runs CSV", pd.DataFrame(summaries).to_csv(index=False), file_name="finsight-all-runs.csv", mime="text/csv")
    y.download_button("Download per-field totals CSV", pd.DataFrame(per_field).to_csv(index=False), file_name="finsight-field-totals.csv", mime="text/csv")


def results_screen(run: Run) -> None:
    page_header("Results", [
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
    cols = [*st.columns(3), *st.columns(3)]
    cols[0].metric("Revenue · PKR m", f'{values["revenue"] / 1000000:,.2f}' if "revenue" in values else "N/A")
    cols[1].metric("Net profit · PKR m", f'{values["net_profit"] / 1000000:,.2f}' if "net_profit" in values else "N/A")
    for col, key in zip(cols[2:], ["return_on_assets", "return_on_equity", "current_ratio", "debt_to_equity"]):
        col.metric(metrics[key].label, display_metric(metrics[key]))
    growth = [metrics[k] for k in ("revenue_growth", "net_profit_growth", "operating_cash_flow_growth") if metrics[k].value is not None]
    if growth:
        for col, metric in zip(st.columns(3), growth):
            col.metric(metric.label, display_metric(metric))
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
    tab_names = ["Overview", "Financial Data", "Ratios", *ROLES, "Final Synthesis", "Sources / Evidence", "Evaluation"]
    tabs = dict(zip(tab_names, st.tabs(tab_names)))
    with tabs["Overview"]:
        st.markdown("### Research workspace")
        st.write(f"{run.company.name} · FY {run.company.financial_year} · {run.company.statement_basis.title()} statements")
        st.success("Human verification saved. All calculations use only the saved verified values.")
        st.write(f"{len(values)} of {len(FIELDS)} fields verified · {sum(m.value is not None for m in run.metrics)} of {len(metrics)} ratios available · {len(run.analysts)} of 4 perspectives complete")
        if run.is_demo:
            st.info("DEMO / SYNTHETIC DATA. Analyst outputs are predefined teaching templates reflecting the saved verified values; no API request is made.")
        else:
            st.info("AI-generated interpretation requires source review. Citations show traceability, not proof that the interpretation is correct.")
        st.markdown("### Accounting checks")
        warnings = validate_run(run)
        for warning in warnings:
            st.warning(warning)
        if not warnings:
            st.caption("No warning from the limited reconciliation checks. This is not an audit.")
        st.caption("Tolerance: greater of PKR 1 or 1% of the larger absolute side. Liquidity/leverage flags are teaching heuristics.")
        if run.company.benchmarks:
            st.markdown("### Supplied benchmark context")
            st.write(run.company.benchmarks)
    with tabs["Financial Data"]:
        reviews = {r.field_name: r for r in run.reviews}
        rows = []
        for f in run.fields:
            r = reviews[f.field_name]
            rows.append({"Field": FIELDS[f.field_name], "Extracted raw": f.raw_value or "N/A", "Extracted unit": f.unit,
                "Extracted normalized": str(f.normalized_value) if f.normalized_value is not None else "N/A",
                "Human verified": str(r.verified_value) if r.verified_value is not None else "N/A", "Internal unit": internal_unit(f.field_name),
                "Decision": r.decision, "Year": r.reporting_year, "Source page": r.source_page, "Review note": r.note})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with tabs["Ratios"]:
        st.caption("Deterministic calculated metrics. The LLM does not calculate these ratios.")
        st.dataframe(pd.DataFrame([{"Metric": m.label, "Result": display_metric(m), "Formula": m.formula,
                                  "Explanation": m.reason} for m in run.metrics]), hide_index=True, width="stretch")
        for m in run.metrics:
            with st.expander(f"{m.label} · {display_metric(m)}"):
                st.code(m.formula, language=None)
                for key in m.inputs:
                    item = registry.get("field:" + key)
                    st.write(item["display"] if item else f"{FIELDS[key]}: unavailable")
                if m.reason:
                    st.caption(m.reason)
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
        a, b, c = st.columns(3)
        with b:
            try:
                content = pdf_report(run)
                st.download_button("Download PDF", content, file_name=f"finsight-{run.id}.pdf", mime="application/pdf", type="primary", width="stretch")
            except (ValueError, OSError, RuntimeError, LayoutError):
                st.warning("PDF export is unavailable. Use Markdown export for this run.")
        a.download_button("Download Markdown", report, file_name=f"finsight-{run.id}.md", mime="text/markdown", width="stretch")
        c.download_button("Download full audit JSON", run.model_dump_json(indent=2), file_name=f"finsight-{run.id}-audit.json", mime="application/json", width="stretch")
    next_button("Next: measure the AI →", STEPS[4], "next_from_results")
