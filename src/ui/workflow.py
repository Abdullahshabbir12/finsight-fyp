"""Small Streamlit workflow screens, separate from financial logic."""
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4
import pandas as pd
import streamlit as st
from src.ai.client import AIClient, AIError
from src.catalog import FIELDS
from src.demo import demo_run
from src.extraction.service import UNITS, extract_fields
from src.models import Company, FinancialField, Run
from src.pdf.reader import candidate_pages, read_pdf, render_page
from src.validation.review import commit_review, review_rows


def set_run(run: Run, pdf: bytes | None = None) -> None:
    st.session_state.run = run
    st.session_state.pdf_bytes = pdf
    st.session_state.workflow_start = perf_counter()
    st.session_state.review_version = st.session_state.get("review_version", 0) + 1


def setup_screen() -> None:
    st.subheader("01 / Company & annual report")
    st.write("Choose a reporting year and statement basis, then upload the annual report.")
    if st.button("Load synthetic demo", type="primary"):
        set_run(demo_run())
        st.rerun()
    with st.form("company"):
        a, b = st.columns(2)
        name = a.text_input("Company name", placeholder="Company legal name")
        ticker = b.text_input("Ticker", placeholder="Optional")
        industry = a.text_input("Industry", placeholder="Manufacturing, banking, ...")
        year = b.number_input("Financial year", 1900, 2200, 2025)
        basis = a.selectbox("Statement basis", ["consolidated", "standalone"])
        benchmark = st.text_area("Optional industry benchmarks", placeholder="Metric, value, unit, period, and source. Leave blank if unavailable.", max_chars=4000)
        upload = st.file_uploader("Annual report PDF (up to 100 MB)", type=["pdf"])
        submitted = st.form_submit_button("Process annual report", type="primary")
    if submitted:
        if not name.strip() or upload is None:
            st.error("Enter a company name and upload a PDF, or load the synthetic demo.")
            return
        try:
            with st.spinner("Reading PDF pages..."):
                content = upload.getvalue()
                pages, warnings, elapsed = read_pdf(content)
            run = Run(id=str(uuid4()), company=Company(name=name.strip(), ticker=ticker.strip(), industry=industry.strip(),
                      financial_year=int(year), statement_basis=basis, benchmarks=benchmark), filename=upload.name,
                      pages=pages, fields=[FinancialField(field_name=k) for k in FIELDS], warnings=warnings,
                      timings={"pdf_seconds": elapsed}, created_at=datetime.now(timezone.utc).isoformat())
            set_run(run, content)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def source_viewer(run: Run, key: str) -> None:
    if not run.pages:
        return
    page = st.selectbox("Inspect physical PDF page", [p.number for p in run.pages], key=key)
    item = next(p for p in run.pages if p.number == page)
    st.text_area("Extracted page text", item.text, height=220, disabled=True, key=key + "_text_" + str(page))
    content = st.session_state.get("pdf_bytes")
    if content and st.checkbox("Show original page image", key=key + "_image"):
        try:
            st.image(render_page(content, page), caption=f"Original annual report · PDF page {page}")
        except (ValueError, RuntimeError):
            st.warning("This page could not be rendered. Open the original PDF manually.")


def processing_screen(run: Run) -> None:
    st.subheader("02 / Document & extraction")
    a, b, c = st.columns(3)
    a.metric("Pages", len(run.pages))
    b.metric("PDF processing", f'{run.timings.get("pdf_seconds", 0):.2f}s')
    c.metric("Readable pages", sum(bool(p.text.strip()) for p in run.pages))
    st.caption(run.filename)
    for warning in run.warnings:
        st.warning(warning)
    if run.is_demo:
        st.info("Synthetic extraction is bundled. Proceed to Human verification.")
    elif run.verified_at:
        st.info("This extraction has been reviewed. Start a new run to re-extract; use Human verification to correct this run.")
    else:
        selected = st.multiselect("Pages to send to AI (review or change the suggested pages)", [p.number for p in run.pages],
                                  default=candidate_pages(run.pages, run.company.statement_basis), key="selected_" + run.id)
        st.caption(f"Suggested: the {run.company.statement_basis} primary statements and the share capital note. Check them against the report's contents page; physical PDF page numbers. Only selected pages are searched. Missing fields can be entered manually during verification.")
        if st.button("Extract financial fields", type="primary", disabled=not selected):
            progress = st.empty()
            try:
                client = AIClient()
                extract_fields(run, selected, client, lambda i, n: progress.info(f"Extracting chunk {i} of {n}..."))
                st.session_state.review_version += 1
                progress.success("Extraction complete. Every value still needs human verification.")
            except AIError as exc:
                progress.error(str(exc))
    with st.expander("Inspect document pages", expanded=False):
        source_viewer(run, "processing_source_" + run.id)


def verification_screen(run: Run) -> None:
    st.subheader("03 / Human verification")
    st.info("Verify every row: accept, edit, or unavailable. Type Verified Value in its Entry Unit, which starts as the statement's own unit. Example: 184,390,517 with PKR thousand. Expenses (cost of sales, finance cost, tax, capex) are positive amounts.")
    st.caption("An edit requires supporting evidence and a review note. Unavailable requires a note explaining why. Accept preserves the original source. Confidence is not proof of correctness. Saving a review clears previous ratios and AI outputs.")
    rows = review_rows(run)
    st.caption("Scroll the table horizontally, or use its fullscreen button, to inspect original values and edit evidence or notes.")
    with st.form("review_form_" + run.id):
        edited = st.data_editor(pd.DataFrame(rows), hide_index=True, width="stretch", height=650,
            key=f"review_{run.id}_{st.session_state.get('review_version', 0)}",
            column_order=["Field", "Decision", "Verified Value", "Entry Unit", "Extracted Value", "Unit", "Page", "Status", "Extraction Notes", "Confidence", "Normalized (base units)", "Verified Year", "Evidence Page", "Evidence Text", "Review Note"],
            disabled=["Field", "Extracted Value", "Unit", "Normalized (base units)", "Page", "Confidence", "Status", "Extraction Notes"],
            column_config={"Decision": st.column_config.SelectboxColumn(options=["pending", "accept", "edit", "unavailable"], required=True),
                           "Verified Value": st.column_config.TextColumn("Verified Value"),
                           "Entry Unit": st.column_config.SelectboxColumn(options=list(UNITS), required=True),
                           "Confidence": st.column_config.ProgressColumn(min_value=0, max_value=1),
                           "Verified Year": st.column_config.NumberColumn(format="%d", step=1)})
        all_accept = st.checkbox("I reviewed every available extracted value against its source; accept them all (remaining rows must be edited or unavailable).")
        save = st.form_submit_button("Save verification", type="primary")
    if save:
        records = edited.to_dict("records")
        if all_accept:
            for f, row in zip(run.fields, records):
                if row["Decision"] == "pending" and f.status == "extracted" and f.normalized_value is not None:
                    row["Decision"] = "accept"
        try:
            commit_review(run, records)
            st.session_state.review_version += 1
            st.success("Verification saved. Continue to Results & analysis.")
        except (ValueError, TypeError, OverflowError) as exc:
            st.error(f"Review was not saved: {exc}")
    with st.expander("Field evidence and extraction warnings"):
        field = st.selectbox("Field", list(FIELDS), format_func=lambda k: FIELDS[k], key="evidence_" + run.id)
        item = next(f for f in run.fields if f.field_name == field)
        st.write(f"PDF page: {item.source_page or 'N/A'} · Extracted year: {item.reporting_year or 'N/A'}")
        st.code(item.source_text or "No extracted evidence. Supply a source when entering a value manually.", language=None)
        for issue in item.issues:
            st.warning(issue)
        for note in item.notes:
            st.info(note)
        source_viewer(run, "verification_source_" + run.id)
