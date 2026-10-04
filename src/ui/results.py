"""Verified values, reproducible metrics and clearly labeled interpretation."""
import json
from time import perf_counter
import pandas as pd
import streamlit as st
from reportlab.platypus import LayoutError
from src.ai.client import AIClient, AIError
from src.ai.council import ROLES, reference_registry, run_council
from src.ai.synthesis import run_synthesis
from src.calculations.ratios import calculate, display_metric
from src.catalog import FIELDS, internal_unit
from src.models import Claim, Run
from src.reporting.export import markdown_report, pdf_report
from src.ui.workflow import source_viewer
from src.utils.evaluation import evaluation
from src.validation.accounting import validate_run
from src.validation.review import verified_values


def show_claim(claim: Claim, registry: dict) -> None:
    st.markdown(f"**{claim.kind}** · {claim.text}")
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


def evaluation_screen(run: Run) -> None:
    stats = evaluation(run)
    st.subheader("Evaluation")
    st.caption("Accuracy compares the original normalized number and reporting year with the saved human review. It is an agreement measure, not independently audited accuracy.")
    a, b, c, d = st.columns(4)
    a.metric("Extraction accuracy", f'{stats["extraction_accuracy"]:.1%}' if stats["extraction_accuracy"] is not None else "N/A")
    b.metric("Extraction completeness", f'{stats["extraction_completeness"]:.1%}')
    c.metric("Numeric / year corrections", stats["numeric_or_year_correction_count"])
    d.metric("Unavailable", stats["unavailable_fields"])
    st.write("Accuracy = correctly extracted fields / fields with a final verified value. Missing extractions later entered manually count as incorrect. Unavailable fields are excluded. Completeness = non-null extracted fields / all predefined fields.")
    st.caption("Observed workflow time includes active-session human review. Processing time sums measured PDF and API stages, including failed attempts. Demo results and timings are illustrative and must be excluded from live extraction evaluation.")
    st.dataframe(pd.DataFrame([{"Measure": k, "Value": "N/A" if v is None else str(v)} for k, v in stats.items()]), hide_index=True, width="stretch")
    st.download_button("Download evaluation JSON", json.dumps(stats, indent=2), file_name=f"finsight-{run.id}-evaluation.json", mime="application/json")
    if run.usage:
        st.dataframe(pd.DataFrame(run.usage), hide_index=True, width="stretch")


def results_screen(run: Run) -> None:
    st.subheader("04 / Results & analysis")
    if not run.verified_at:
        st.info("Complete Human verification and save it before calculating ratios or running AI analysis.")
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
    st.caption("Cards: verified revenue and profit; ratios calculated in Python. Returns use year-end balances. AI outputs below are interpretations.")
    st.divider()
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
        evaluation_screen(run)
    st.divider()
    st.subheader("Export research report")
    st.caption("Exports include verified data, Python calculations, completed interpretations, source evidence and limitations. Incomplete AI analysis is labeled as a partial report.")
    report = markdown_report(run)
    a, b, c = st.columns(3)
    a.download_button("Download Markdown", report, file_name=f"finsight-{run.id}.md", mime="text/markdown")
    with b:
        try:
            content = pdf_report(run)
            st.download_button("Download PDF", content, file_name=f"finsight-{run.id}.pdf", mime="application/pdf")
        except (ValueError, OSError, RuntimeError, LayoutError):
            st.warning("PDF export is unavailable. Use Markdown export for this run.")
    c.download_button("Download full audit JSON", run.model_dump_json(indent=2), file_name=f"finsight-{run.id}-audit.json", mime="application/json")
