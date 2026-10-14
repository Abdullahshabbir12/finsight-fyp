"""One report body for Markdown and a paginated PDF with internal evidence links."""
from html import escape
from io import BytesIO
import re
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from src.ai.council import reference_registry, render_text
from src.calculations.ratios import display_metric
from src.catalog import FIELDS, internal_unit
from src.models import Claim, Run
from src.validation.accounting import validate_run
from src.validation.review import verified_values

DISCLAIMER = "Decision-support prototype for academic research. Human verification is not an audit. AI interpretations may be incomplete or incorrect. This report does not provide investment recommendations or replace professional judgment."


def clean(value) -> str:
    return str(value).replace("|", "/").replace("\n", " ").replace("\r", " ").replace("<", "(").replace(">", ")")


def anchor(ref: str) -> str:
    return ref.replace(":", "-")


def claim_markdown(claim: Claim, registry: dict) -> str:
    links = ", ".join(f"[{ref}](#{anchor(ref)})" for ref in claim.references)
    return f"- **{claim.kind}**: {clean(render_text(claim.text, registry))}" + (f" Sources: {links}." if links else "")


def markdown_report(run: Run) -> str:
    verified_values(run)
    if not run.metrics:
        raise ValueError("Calculate verified metrics before exporting.")
    c = run.company
    registry = reference_registry(run)
    lines = ["# FinSight | Financial Research", "", f"**Company:** {clean(c.name)} ({clean(c.ticker)})",
             f"**Financial year:** {c.financial_year} | **Industry:** {clean(c.industry)} | **Basis:** {c.statement_basis}",
             f"**Document:** {clean(run.filename)}" + (f" | **Source:** {clean(run.source)}" if run.source else ""), f"**Run:** {run.id}", f"**Verification saved:** {run.verified_at}", "",
             "**DEMO / SYNTHETIC DATA**" if run.is_demo else "**Human-verified data with AI-generated interpretation**", "",
             "**Status:** " + ("Final synthesis available; human review required." if run.synthesis else "Partial report: AI council or final synthesis is incomplete."),
             "", "## Verified Financial Data", "",
             "Original extraction and final human values are shown separately. All verified monetary values use base PKR; EPS uses PKR/share and shares use counts.", "",
             "| Field | Extracted value / unit | Human-verified value | Unit | Decision |", "|---|---|---|---|---|"]
    reviews = {r.field_name: r for r in run.reviews}
    for f in run.fields:
        r = reviews[f.field_name]
        value = f"{r.verified_value:,.2f}" if r.verified_value is not None else "N/A"
        lines.append(f"| {FIELDS[f.field_name]} | {clean(f.raw_value or 'N/A')} / {clean(f.unit)} | {value} | {internal_unit(f.field_name)} | {r.decision} |")
    lines += ["", "### Unavailable fields: review notes", ""]
    lines += [f"- **{FIELDS[r.field_name]}**: {clean(r.explanation() or 'No supported value available.')}"
              for r in run.reviews if r.decision == "unavailable"]
    lines += ["", "## Deterministic Financial Ratios", "", "Computed by Python from verified values. Single-year returns and turnover use year-end balances; average-balance versions and growth rates use the verified prior-year comparatives.", "",
              "| Metric | Result | Formula / N/A reason |", "|---|---|---|"]
    for m in run.metrics:
        lines.append(f"| {m.label} | {display_metric(m)} | {clean(m.formula)}{'; ' + clean(m.reason) if m.reason else ''} |")
    lines += ["", "## Validation / Reconciliation", ""]
    warnings = validate_run(run)
    lines += ["- " + clean(w) for w in warnings] or ["No warnings from the limited accounting checks. This is not an audit."]
    lines += ["", "## AI Council", "", "Sample template outputs (offline synthetic demo)." if run.is_demo else "AI-generated interpretation; check the cited evidence."]
    for name, result in run.analysts.items():
        lines += ["", "### " + name, "", claim_markdown(result.overall_observation, registry)]
        for title, claims in [("Positive factors", result.positive_factors), ("Risk factors", result.risk_factors), ("Limitations", result.limitations)]:
            lines += ["", "**" + title + "**"]
            lines += [claim_markdown(claim, registry) for claim in claims] or ["- None identified in this output."]
        if result.key_metrics:
            lines += ["", "Key references: " + ", ".join(f"[{r}](#{anchor(r)})" for r in result.key_metrics)]
    if not run.analysts:
        lines += ["No AI perspectives generated."]
    lines += ["", "## Final Synthesis", ""]
    if run.synthesis:
        for section in run.synthesis.sections:
            lines += ["### " + section.heading, ""] + [claim_markdown(c, registry) for c in section.claims] + [""]
    else:
        lines += ["Not generated. This export is a partial report."]
    lines += ["", "## Sources / Evidence", "", "Page numbers refer to physical PDF pages, which may differ from printed page labels. Corrected values and notes reflect the human review."]
    for ref, item in registry.items():
        lines += ["", f'<a id="{anchor(ref)}"></a>', "### " + ref, "", clean(item["display"])]
        if item.get("source_text"):
            lines.append("Source excerpt / supplied context: " + clean(item["source_text"]))
        if item.get("review_note"):
            lines.append("Human review note: " + clean(item["review_note"]))
        if item.get("inputs"):
            lines.append("Inputs: " + ", ".join(f"[{r}](#{anchor(r)})" for r in item["inputs"]))
    lines += ["", "## Limitations and Human Review", "", DISCLAIMER, "",
              "- Only selected PDF pages were submitted for live extraction; omissions may remain.",
              "- At most two financial years are captured; one year of growth does not establish a trend or future performance.",
              "- Financial ratios for banks, insurers and other specialized industries may require different definitions.",
              "- Financial-quality indicators require further investigation; they are not findings of wrongdoing.",
              "- Benchmarks, when supplied, have not been independently verified.",
              "- Reconciliation tolerance is the greater of PKR 1 and 1% of the larger absolute side."]
    return "\n".join(lines) + "\n"


def pdf_report(run: Run) -> bytes:
    """Flowable paragraphs/tables wrap long evidence instead of clipping it."""
    markdown = markdown_report(run)
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="FinBody", fontName="Helvetica", fontSize=9, leading=12, spaceAfter=6, textColor=colors.HexColor("#172b46")))
    styles.add(ParagraphStyle(name="FinCell", parent=styles["FinBody"], fontSize=7, leading=10, spaceAfter=0, alignment=TA_LEFT))
    for heading in ("Title", "Heading2", "Heading3", "Heading4"):
        styles[heading].textColor = colors.HexColor("#087f8c")
        styles[heading].keepWithNext = True
    body = []
    def paragraph(text, style="FinBody"):
        text = text.replace("—", "-").replace("≈", "~").replace("→", "to")
        safe = escape(text)
        safe = re.sub(r"\[([^\]]+)\]\(#([a-z0-9_-]+)\)", r'<link href="#\2" color="#087f8c">\1</link>', safe)
        safe = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", safe)
        return Paragraph(safe, styles[style])
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("| "):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not lines[i].startswith("|---"):
                    rows.append([paragraph(cell.strip(), "FinCell") for cell in lines[i].strip("|").split("|")])
                i += 1
            widths = [115, 115, 110, 60, 52] if len(rows[0]) == 5 else [125, 65, 262]
            table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3f1f3")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fa")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6), ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#087f8c"))]))
            body.extend([table, Spacer(1, 12)])
            continue
        match = re.fullmatch(r'<a id="([a-z0-9_-]+)"></a>', line)
        if match:
            body.append(Paragraph(f'<a name="{match.group(1)}"/>', styles["FinBody"]))
        elif line.startswith("# "):
            body.append(paragraph(line[2:], "Title"))
        elif line.startswith("## "):
            body.append(paragraph(line[3:], "Heading2"))
        elif line.startswith("### "):
            body.append(paragraph(line[4:], "Heading3"))
        elif line.startswith("**") and line.endswith("**") and line.count("**") == 2:
            body.append(paragraph(line[2:-2], "Heading4"))
        elif line:
            body.append(paragraph(line))
        i += 1
    # Keep each short evidence entry together across page boundaries.
    grouped = []
    evidence_block = []
    for item in body:
        is_anchor = isinstance(item, Paragraph) and item.text.startswith('<a name=')
        is_section = isinstance(item, Paragraph) and item.style.name == "Heading2"
        if evidence_block and (is_anchor or is_section):
            grouped.append(KeepTogether(evidence_block))
            evidence_block = []
        if is_anchor or evidence_block:
            evidence_block.append(item)
        else:
            grouped.append(item)
    if evidence_block:
        grouped.append(KeepTogether(evidence_block))
    body = grouped
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(54, 30, "FinSight | " + ("DEMO / SYNTHETIC DATA" if run.is_demo else "Human review required"))
        canvas.drawRightString(558, 30, f"Page {doc.page}")
        canvas.restoreState()
    doc = SimpleDocTemplate(buffer, pagesize=(612, 792), rightMargin=54, leftMargin=54,
                            topMargin=48, bottomMargin=50, title="FinSight Financial Research", author="FinSight")
    doc.build(body, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
