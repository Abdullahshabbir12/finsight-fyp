"""Small Streamlit workflow screens, separate from financial logic."""
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4
import pandas as pd
import streamlit as st
from src.ai.client import AIClient, AIError
from src.catalog import LABELS, catalog
import sqlite3
from src.database.store import list_runs, load_run
from src.demo import demo_run
from src.extraction.service import UNITS, extract_fields
from src.models import Company, FinancialField, Run
from src.pdf.reader import BANK_WARNING, candidate_pages, looks_like_bank, read_pdf, render_page, statement_bases
from src.ui.layout import STEPS, flash, next_button, page_header, request_step, show_flash
from src.validation.review import (REASONS, UNAVAILABLE_REASONS, ReviewError, accept_ready, commit_review,
                                   mark_remaining_unavailable, review_rows, save_draft)

# Only the columns needed to decide; evidence details live in the panel under the table.
VISIBLE = ["Field", "Status", "AI value", "Decision", "Verified Value", "Entry Unit", "Reason",
           "Evidence Page", "Evidence Text", "Review Note"]


def set_run(run: Run, pdf: bytes | None = None) -> None:
    st.session_state.run = run
    st.session_state.pdf_bytes = pdf
    st.session_state.workflow_start = perf_counter()
    st.session_state.review_version = st.session_state.get("review_version", 0) + 1


SECTOR_CHOICES = {"Detect automatically": "auto", "Non-financial company": "general", "Bank": "bank"}


def start_run(content: bytes, filename: str, name: str, ticker: str, industry: str, year: int, basis: str,
              benchmark: str, source: str = "", sector: str = "auto") -> None:
    """Read the PDF, settle the statement basis and company type, and open the Extract step."""
    with st.spinner("Reading PDF pages..."):
        pages, warnings, elapsed = read_pdf(content)
    found = statement_bases(pages)
    if basis == "auto":
        basis = "consolidated" if "consolidated" in found else "standalone"
        flash("info", f"Statement basis set to **{basis}**: it is what this report's primary statements show.")
    elif found and basis not in found:
        # Extracting the wrong basis flags every value as a mismatch; say so and use what the report contains.
        flash("warning", f"You chose {basis}, but this report only contains {', '.join(sorted(found))} statements, "
                         f"so FinSight switched to **{sorted(found)[0]}**.")
        basis = sorted(found)[0]
    bank = looks_like_bank(pages, industry)
    if sector == "auto":
        sector = "bank" if bank else "general"
        if bank:
            flash("info", "🏦 **Bank detected.** FinSight uses its bank fields: interest income, deposits, advances, "
                          "non-performing loans and capital adequacy.")
    elif sector == "general" and bank:
        warnings.insert(0, BANK_WARNING)
    run = Run(id=str(uuid4()), company=Company(name=name.strip(), ticker=ticker.strip(), industry=industry.strip(),
              financial_year=int(year), statement_basis=basis, benchmarks=benchmark, sector=sector),
              filename=filename, source=source,
              pages=pages, fields=[FinancialField(field_name=k) for k in catalog(sector)], warnings=warnings,
              timings={"pdf_seconds": elapsed}, created_at=datetime.now(timezone.utc).isoformat())
    set_run(run, content)
    request_step(STEPS[1])
    st.rerun()


PSX_LIBRARY = "https://financials.psx.com.pk/"


def find_report_help() -> None:
    """Where to get a report. PSX's terms forbid automated access, so FinSight links instead of fetching."""
    with st.container(border=True):
        st.markdown("**Don't have the PDF yet?**")
        st.markdown("1. Open PSX's financial reports library, choose the company, then **Annual** for your year.\n"
                    "2. Save the PDF, then drop it in the box below and fill in the company details.")
        st.link_button("Open PSX financial reports ↗", PSX_LIBRARY, width="stretch")
        st.caption("Most companies also publish annual reports on their own websites under Investor Relations.")


def upload_tab() -> None:
    with st.form("company"):
        a, b = st.columns(2)
        name = a.text_input("Company name", placeholder="e.g. Engro Fertilizers Limited")
        ticker = b.text_input("Ticker", placeholder="Optional")
        industry = a.text_input("Industry", placeholder="e.g. Cement, Textiles")
        year = b.number_input("Financial year", 1900, 2200, 2025, help="The year the reporting period ends in.")
        basis = a.selectbox("Statement basis", ["consolidated", "standalone"],
                            help="If the report does not contain the basis you choose, FinSight switches and tells you.")
        sector = b.selectbox("Company type", list(SECTOR_CHOICES),
                             help="Banks get their own fields and ratios. Detection looks for bank-only lines such as deposits.")
        with st.expander("Optional: industry benchmarks"):
            benchmark = st.text_area("Benchmarks", placeholder="Metric, value, unit, period, and source.", max_chars=4000,
                                     label_visibility="collapsed")
        upload = st.file_uploader("Annual report PDF (up to 100 MB)", type=["pdf"])
        submitted = st.form_submit_button("Read the report", type="primary", width="stretch")
    if submitted:
        if not name.strip() or upload is None:
            st.error("Enter a company name and upload a PDF, or load the synthetic demo.")
            return
        try:
            start_run(upload.getvalue(), upload.name, name, ticker, industry, int(year), basis, benchmark,
                      sector=SECTOR_CHOICES[sector])
        except ValueError as exc:
            st.error(str(exc))


def setup_screen() -> None:
    show_flash()
    page_header("Start an analysis", [
        "New here? Try the **synthetic demo** first: it walks through every step with sample data.",
        "For a real report, upload its annual report PDF. Don't have it? Use **Open PSX financial reports** to download it first.",
        "Banks are supported: FinSight detects them and uses bank fields (deposits, advances, capital adequacy).",
    ])
    demo, start = st.columns([1, 2], gap="large")
    with demo:
        with st.container(border=True):
            st.markdown("**Just exploring?**")
            st.caption("A fictional company with prepared values. No API key or PDF needed.")
            if st.button("Load synthetic demo", type="primary", width="stretch"):
                set_run(demo_run())
                request_step(STEPS[2])
                st.rerun()
        saved_runs_card()
    with start:
        find_report_help()
        with st.container(border=True):
            st.markdown("**Analyse an annual report**")
            upload_tab()


def saved_runs_card() -> None:
    with st.container(border=True):
        st.markdown("**Open a saved analysis**")
        try:
            saved = list_runs()
        except (OSError, sqlite3.Error, ValueError):
            st.caption("Saved runs are unavailable on this computer.")
            return
        if not saved:
            st.caption("Nothing saved yet. Use 💾 Save run at the top once you have a run.")
            return
        names = {r[0]: f"{'DEMO · ' if r[3] else ''}{r[1]} · {r[2][:10]}" for r in saved}
        selected = st.selectbox("Saved analyses", list(names), format_func=names.get, label_visibility="collapsed")
        if st.button("Open", width="stretch"):
            set_run(load_run(selected))
            request_step(STEPS[3])
            st.rerun()


def page_image(page: int, key: str) -> None:
    content = st.session_state.get("pdf_bytes")
    if content and st.toggle(f"Show PDF page {page}", key=key):
        try:
            st.image(render_page(content, page), caption=f"Original annual report · PDF page {page}")
        except (ValueError, RuntimeError):
            st.warning("This page could not be rendered. Open the original PDF manually.")


def source_viewer(run: Run, key: str) -> None:
    if not run.pages:
        return
    page = st.selectbox("PDF page", [p.number for p in run.pages], key=key)
    item = next(p for p in run.pages if p.number == page)
    st.text_area("Page text", item.text, height=220, disabled=True, key=key + "_text_" + str(page))
    page_image(page, key + "_image")


def extraction_summary(run: Run) -> None:
    counts = {s: sum(f.status == s for f in run.fields) for s in ("extracted", "needs_review", "missing")}
    a, b, c = st.columns(3)
    a.metric("🟢 Ready", counts["extracted"], help="Passed every check; you still confirm them.")
    b.metric("🟠 Check", counts["needs_review"], help="A number was found but a check flagged it.")
    c.metric("⚪ Missing", counts["missing"], help="Not found as a single printed figure; enter it or mark it unavailable.")


def processing_screen(run: Run) -> None:
    show_flash()
    page_header("Find the numbers", [
        "FinSight suggests the pages holding the financial statements. Compare them with the report's contents page.",
        "Click **Extract financial fields**. The AI proposes each value with its page and a quote; nothing is final yet.",
        "Then go to **Verify** to check every value.",
    ])
    if BANK_WARNING in run.warnings:
        st.error("🏦 " + BANK_WARNING)
    a, b, c = st.columns(3)
    a.metric("Pages", len(run.pages))
    b.metric("Readable pages", sum(bool(p.text.strip()) for p in run.pages))
    c.metric("Read in", f'{run.timings.get("pdf_seconds", 0):.1f}s')
    st.caption(run.filename + (f" · source: {run.source}" if run.source else ""))
    notes = [w for w in run.warnings if w != BANK_WARNING]
    if notes:
        with st.expander(f"Notes about this PDF ({len(notes)})"):
            for warning in notes:
                st.warning(warning)
    if run.is_demo:
        st.success("The demo's values are already extracted.")
        next_button("Next: verify the numbers →", STEPS[2], "next_from_demo_extract")
    elif run.verified_at:
        st.info("This run has been verified. Start a new run to extract again, or correct values in Verify.")
        next_button("Next: results →", STEPS[3], "next_from_verified_extract")
    else:
        selected = st.multiselect("Pages to send to the AI", [p.number for p in run.pages],
                                  default=candidate_pages(run.pages, run.company.statement_basis, sector=run.company.sector), key="selected_" + run.id,
                                  help="Physical PDF page numbers, which may differ from the printed page labels.")
        if st.button("Extract financial fields", type="primary", disabled=not selected):
            progress = st.empty()
            try:
                client = AIClient()
                extract_fields(run, selected, client, lambda i, n: progress.info(f"Reading page {i} of {n}..."))
                st.session_state.review_version += 1
                progress.success("Extraction complete. Every value still needs your check.")
            except AIError as exc:
                progress.error(str(exc))
        if any(f.status != "missing" for f in run.fields):
            extraction_summary(run)
            next_button("Next: verify the numbers →", STEPS[2], "next_from_extract")
    with st.expander("Browse the document"):
        source_viewer(run, "processing_source_" + run.id)


def problem_summary(problems: list[str]) -> str:
    """Group identical problems so 20 pending rows read as one line, not twenty."""
    groups: dict[str, list[str]] = {}
    for problem in problems:
        field, _, message = problem.partition(": ")
        groups.setdefault(message or field, []).append(field if message else "")
    lines = [f"- **{message[0].upper() + message[1:]}** ({len(fields)} row{'s' if len(fields) > 1 else ''}): {', '.join(f for f in fields if f)}"
             for message, fields in groups.items()]
    tip = "\n\nTip: **Accept all ready** and **Mark remaining unavailable** decide many rows at once." if any("choose accept" in m for m in groups) else ""
    return f"**{len(problems)} row{'s' if len(problems) > 1 else ''} need attention** before verification can finish:\n" + "\n".join(lines) + tip


def verification_screen(run: Run) -> None:
    show_flash()
    page_header("Check the numbers", [
        "For each row choose **accept** (correct as found), **edit** (fix it) or **unavailable** (not in the report).",
        "Shortcut: **Accept all ready** accepts every 🟢 row; **Mark remaining unavailable** fills the rest with one reason.",
        "Edits need a quote or source in **Evidence** and a **Reason**. Type values in the unit shown; expenses are positive.",
    ])
    rows = review_rows(run)
    decided = sum(r["Decision"] != "pending" for r in rows)
    finished = bool(run.verified_at) and not run.review_draft
    st.progress(decided / len(rows), text=f"{decided} of {len(rows)} rows decided" + (" · verification finished ✓" if finished else ""))
    problems = st.session_state.pop("review_problems", None)
    if problems:
        st.error(problem_summary(problems))
    with st.form("review_form_" + run.id):
        edited = st.data_editor(pd.DataFrame(rows), hide_index=True, width="stretch", height=min(38 * len(rows) + 40, 720),
            key=f"review_{run.id}_{st.session_state.get('review_version', 0)}", column_order=VISIBLE,
            disabled=["Field", "Status", "AI value"],
            column_config={
                "Field": st.column_config.TextColumn("Field", pinned=True, width="medium"),
                "Status": st.column_config.TextColumn("Status", width="small"),
                "AI value": st.column_config.TextColumn("AI value", width="medium", help="Number, unit and PDF page found by the AI."),
                "Decision": st.column_config.SelectboxColumn("Decision", options=["pending", "accept", "edit", "unavailable"], required=True, width="small"),
                "Verified Value": st.column_config.TextColumn("Your value", help="Type in the unit in the next column."),
                "Entry Unit": st.column_config.SelectboxColumn("Unit", options=list(UNITS), required=True, width="small"),
                "Reason": st.column_config.SelectboxColumn("Reason", options=REASONS, width="medium",
                                                          help="Required for edit and unavailable."),
                "Evidence Page": st.column_config.TextColumn("Page", width="small"),
                "Evidence Text": st.column_config.TextColumn("Evidence", width="medium", help="Quote from the report, or where the value came from."),
                "Review Note": st.column_config.TextColumn("Note", width="medium", help="Optional, unless the reason is Other."),
            })
        reason = st.selectbox("Reason used by 'Mark remaining unavailable'", UNAVAILABLE_REASONS)
        a, b, c, d = st.columns(4)
        accept_all = a.form_submit_button("✓ Accept all ready", width="stretch")
        mark_rest = b.form_submit_button("Mark remaining unavailable", width="stretch")
        save = c.form_submit_button("Save progress", width="stretch")
        finish = d.form_submit_button("Finish verification", type="primary", width="stretch")
    if accept_all or mark_rest or save or finish:
        records = edited.to_dict("records")
        if accept_all:
            flash("success", f"Accepted {accept_ready(run, records)} ready values. Check them against the PDF before finishing.")
        if mark_rest:
            flash("info", f"Marked {mark_remaining_unavailable(records, reason)} remaining rows unavailable.")
        if finish:
            try:
                commit_review(run, records)
                flash("success", "Verification finished. Ratios and AI analysis now use only these verified values.")
            except ReviewError as exc:
                save_draft(run, records)
                st.session_state.review_problems = exc.problems
            except (ValueError, TypeError, OverflowError) as exc:
                save_draft(run, records)
                st.session_state.review_problems = [str(exc)]
        else:
            save_draft(run, records)
            if save:
                flash("success", "Progress saved. Finish verification when every row has a decision.")
        st.session_state.review_version += 1
        st.rerun()
    if finished:
        next_button("Next: results →", STEPS[3], "next_from_verify")
    with st.container(border=True):
        st.markdown("**🔍 Check a field against the PDF**")
        field = st.selectbox("Field", [f.field_name for f in run.fields], format_func=lambda k: LABELS[k], key="evidence_" + run.id)
        item = next(f for f in run.fields if f.field_name == field)
        st.write(f"AI value: **{item.raw_value or 'not found'}** {item.unit if item.raw_value else ''} · "
                 f"PDF page {item.source_page or '—'} · year {item.reporting_year or '—'}")
        st.code(item.source_text or "No quote extracted. Enter the value from the report with your own evidence.", language=None)
        for issue in item.issues:
            st.warning(issue)
        for note in item.notes:
            st.info(note)
        if item.source_page:
            page_image(item.source_page, f"field_page_{run.id}_{field}")
    with st.expander("Browse all pages"):
        source_viewer(run, "verification_source_" + run.id)
