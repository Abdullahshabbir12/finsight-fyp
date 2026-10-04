"""The only gate from extracted proposals to calculation inputs."""
from datetime import datetime, timezone
from decimal import Decimal
from src.catalog import FIELDS
from src.extraction.service import parse_number
from src.models import Review, Run


def review_rows(run: Run) -> list[dict]:
    existing = {r.field_name: r for r in run.reviews}
    rows = []
    for f in run.fields:
        r = existing.get(f.field_name)
        rows.append({"Field": FIELDS[f.field_name], "Extracted Value": f.raw_value or "N/A",
                     "Unit": f.unit, "Normalized (base units)": str(f.normalized_value) if f.normalized_value is not None else "N/A",
                     "Page": f.source_page, "Confidence": f.confidence, "Status": f.status,
                     "Decision": r.decision if r else "pending",
                     "Verified Value": str(r.verified_value) if r and r.verified_value is not None else str(f.normalized_value) if f.normalized_value is not None else "",
                     "Verified Year": r.reporting_year if r else run.company.financial_year,
                     "Evidence Page": str(r.source_page or "") if r else str(f.source_page or ""),
                     "Evidence Text": r.source_text if r else f.source_text,
                     "Review Note": r.note if r else ""})
    return rows


def commit_review(run: Run, rows: list[dict]) -> None:
    if len(rows) != len(FIELDS) or len(run.fields) != len(FIELDS):
        raise ValueError("The complete field catalogue must be reviewed.")
    reviews = []
    for f, row in zip(run.fields, rows):
        label = FIELDS[f.field_name]
        decision = row["Decision"]
        if decision not in {"accept", "edit", "unavailable"}:
            raise ValueError(f"{label}: choose accept, edit or unavailable.")
        year = int(row["Verified Year"])
        if year != run.company.financial_year:
            raise ValueError(f"{label}: verified year must match the selected reporting year.")
        value = None
        page = None
        source = ""
        note = str(row.get("Review Note") or "").strip()
        if decision != "unavailable":
            value = parse_number(str(row["Verified Value"]))
            if decision == "accept":
                if f.normalized_value is None or f.status != "extracted" or f.reporting_year != year:
                    raise ValueError(f"{label}: no valid extraction to accept. Use edit with evidence, or unavailable.")
                if value != f.normalized_value:
                    raise ValueError(f"{label}: changed values require the edit decision.")
                page, source = f.source_page, f.source_text
            else:
                raw_page = str(row.get("Evidence Page") or "").strip()
                page = int(raw_page) if raw_page else None
                source = str(row.get("Evidence Text") or "").strip()
                if not source or not note:
                    raise ValueError(f"{label}: edited values need evidence text and a review note explaining the correction or manual entry.")
                if page is None and not note:
                    raise ValueError(f"{label}: identify the manual source in your note.")
            if page is not None and page not in {p.number for p in run.pages}:
                raise ValueError(f"{label}: evidence page is outside this document.")
        reviews.append(Review(field_name=f.field_name, decision=decision, verified_value=value,
                              reporting_year=year, source_page=page, source_text=source, note=note))
    # Commit atomically: an error above must not leave a partly reviewed run.
    run.reviews = reviews
    run.verified_at = datetime.now(timezone.utc).isoformat()
    run.metrics = []
    run.analysts = {}
    run.synthesis = None


def verified_values(run: Run) -> dict[str, Decimal]:
    if not run.verified_at or {r.field_name for r in run.reviews} != set(FIELDS) or len(run.reviews) != len(FIELDS):
        raise ValueError("Complete and save human verification before calculating or analyzing.")
    values = {}
    for r in run.reviews:
        if r.reporting_year != run.company.financial_year:
            raise ValueError("Verified reporting year does not match the run.")
        if r.decision != "unavailable" and r.verified_value is not None:
            if not r.verified_value.is_finite():
                raise ValueError("Verified values must be finite.")
            values[r.field_name] = r.verified_value
    return values
