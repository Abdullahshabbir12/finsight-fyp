"""The only gate from extracted proposals to calculation inputs."""
from datetime import datetime, timezone
from decimal import Decimal
from src.catalog import FIELDS, expected_year, internal_unit
from src.extraction.service import UNITS, allowed_units, parse_number
from src.models import Review, Run

# Reasons are picked from lists, so reviewers do not have to type, and corrections can be counted by type.
UNAVAILABLE_REASONS = ["Not reported in this document", "Not reported as a single line", "Not applicable to this company"]
EDIT_REASONS = ["Wrong number", "Wrong unit or scale", "Wrong year or column", "Wrong sign",
                "Missing - entered manually", "Flagged - confirmed manually"]
OTHER_REASON = "Other (explain in note)"
REASONS = ["", *UNAVAILABLE_REASONS, *EDIT_REASONS, OTHER_REASON]
EDITABLE = ["Decision", "Verified Value", "Entry Unit", "Reason", "Evidence Page", "Evidence Text", "Review Note"]
STATUS_LABEL = {"extracted": "🟢 Ready", "needs_review": "🟠 Check", "missing": "⚪ Missing"}


class ReviewError(ValueError):
    """Every problem in a review at once, so the reviewer can fix them in one pass."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(" ".join(problems))


def plain(value: Decimal) -> str:
    """Show a Decimal without exponent notation, e.g. 184390517 rather than 1.84390517E+8."""
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def cell(value) -> str:
    """Table cells arrive as None, NaN, floats or text; normalise them to clean text."""
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:  # NaN from an empty cell
            return ""
        return str(int(value)) if value.is_integer() else plain(Decimal(str(value)))
    return str(value).strip()


def entry_unit(field) -> str:
    """Reviewers type values in the statement's own unit, avoiding hand-added zeros."""
    return field.unit if field.unit in allowed_units(field.field_name) else internal_unit(field.field_name)


def ai_value(field) -> str:
    if field.raw_value is None:
        return "—"
    page = f" · p{field.source_page}" if field.source_page else ""
    return f"{field.raw_value} {field.unit}{page}"


def review_rows(run: Run) -> list[dict]:
    existing = {r.field_name: r for r in run.reviews}
    draft = {d.get("field"): d for d in run.review_draft}
    rows = []
    for f in run.fields:
        r = existing.get(f.field_name)
        # Saved reviews are stored in base units; new reviews start in the statement unit.
        unit = internal_unit(f.field_name) if r else entry_unit(f)
        if r and r.verified_value is not None:
            value = plain(r.verified_value)
        elif not r and f.normalized_value is not None:
            value = plain(f.normalized_value / UNITS[unit])
        else:
            value = ""
        row = {"Field": FIELDS[f.field_name], "Status": STATUS_LABEL[f.status], "AI value": ai_value(f),
               "Extracted Value": f.raw_value or "N/A", "Unit": f.unit,
               "Normalized (base units)": str(f.normalized_value) if f.normalized_value is not None else "N/A",
               "Page": f.source_page, "Confidence": f.confidence,
               "Extraction Notes": " ".join(f.issues + f.notes),
               "Decision": r.decision if r else "pending",
               "Verified Value": value, "Entry Unit": unit, "Reason": r.reason if r else "",
               "Verified Year": r.reporting_year if r else expected_year(f.field_name, run.company.financial_year),
               "Evidence Page": str(r.source_page or "") if r else str(f.source_page or ""),
               "Evidence Text": r.source_text if r else f.source_text,
               "Review Note": r.note if r else ""}
        if f.field_name in draft:
            row.update({k: draft[f.field_name].get(k, row[k]) for k in EDITABLE})
        rows.append(row)
    return rows


def save_draft(run: Run, rows: list[dict]) -> None:
    """Keep unfinished decisions without validating them ("Save progress")."""
    run.review_draft = [{"field": f.field_name, **{k: cell(row.get(k)) for k in EDITABLE}} for f, row in zip(run.fields, rows)]


def accept_ready(run: Run, rows: list[dict]) -> int:
    """Accept every pending row whose extraction passed all checks; returns how many changed."""
    changed = 0
    for f, row in zip(run.fields, rows):
        if cell(row.get("Decision")) == "pending" and f.status == "extracted" and f.normalized_value is not None:
            unit = entry_unit(f)
            row.update({"Decision": "accept", "Entry Unit": unit, "Verified Value": plain(f.normalized_value / UNITS[unit])})
            changed += 1
    return changed


def mark_remaining_unavailable(rows: list[dict], reason: str) -> int:
    changed = 0
    for row in rows:
        if cell(row.get("Decision")) == "pending":
            row.update({"Decision": "unavailable", "Reason": reason})
            changed += 1
    return changed


def commit_review(run: Run, rows: list[dict]) -> None:
    if len(rows) != len(FIELDS) or len(run.fields) != len(FIELDS):
        raise ValueError("The complete field catalogue must be reviewed.")
    reviews, problems = [], []
    pages = {p.number for p in run.pages}
    for f, row in zip(run.fields, rows):
        label = FIELDS[f.field_name]
        decision, reason, note = cell(row.get("Decision")), cell(row.get("Reason")), cell(row.get("Review Note"))
        year_text = cell(row.get("Verified Year")) or str(expected_year(f.field_name, run.company.financial_year))
        year = int(year_text) if year_text.isdigit() else 0
        if decision not in {"accept", "edit", "unavailable"}:
            problems.append(f"{label}: choose accept, edit or unavailable.")
            continue
        if year != expected_year(f.field_name, run.company.financial_year):
            problems.append(f"{label}: verified year must be {expected_year(f.field_name, run.company.financial_year)}.")
            continue
        value, page, source = None, None, ""
        if decision == "unavailable":
            if not (reason in UNAVAILABLE_REASONS or note):
                problems.append(f"{label}: choose why the value is unavailable in the Reason column (or explain in Note).")
                continue
        else:
            unit = cell(row.get("Entry Unit")) or internal_unit(f.field_name)
            if unit not in allowed_units(f.field_name):
                problems.append(f"{label}: Entry Unit must be one of {', '.join(allowed_units(f.field_name))}.")
                continue
            try:
                value = parse_number(cell(row.get("Verified Value"))) * UNITS[unit]
            except ValueError:
                problems.append(f"{label}: enter a number such as 1,234,567 or (1,234).")
                continue
            if decision == "accept":
                if f.normalized_value is None or f.status != "extracted" or f.reporting_year != year:
                    problems.append(f"{label}: no valid extraction to accept. Use edit with evidence, or unavailable.")
                    continue
                if value != f.normalized_value:
                    problems.append(f"{label}: changed values require the edit decision.")
                    continue
                page, source = f.source_page, f.source_text
            else:
                raw_page = cell(row.get("Evidence Page"))
                page = int(raw_page) if raw_page.isdigit() else None
                source = cell(row.get("Evidence Text"))
                if not source or not (reason in EDIT_REASONS or note):
                    problems.append(f"{label}: edited values need evidence text (a quote or source) and a reason, or a note explaining the correction.")
                    continue
                if raw_page and page is None:
                    problems.append(f"{label}: evidence page must be a page number.")
                    continue
            if page is not None and page not in pages:
                problems.append(f"{label}: evidence page {page} is outside this document.")
                continue
        if reason == OTHER_REASON and not note:
            problems.append(f"{label}: explain 'Other' in the Note column.")
            continue
        reviews.append(Review(field_name=f.field_name, decision=decision, verified_value=value, reporting_year=year,
                              source_page=page, source_text=source, note=note,
                              reason=reason if decision != "accept" else ""))
    if problems:
        raise ReviewError(problems)
    # Commit atomically: an error above must not leave a partly reviewed run.
    run.reviews = reviews
    run.review_draft = []
    run.verified_at = datetime.now(timezone.utc).isoformat()
    run.metrics = []
    run.analysts = {}
    run.synthesis = None


def verified_values(run: Run) -> dict[str, Decimal]:
    if not run.verified_at or {r.field_name for r in run.reviews} != set(FIELDS) or len(run.reviews) != len(FIELDS):
        raise ValueError("Complete and save human verification before calculating or analyzing.")
    values = {}
    for r in run.reviews:
        if r.reporting_year != expected_year(r.field_name, run.company.financial_year):
            raise ValueError("Verified reporting year does not match the run.")
        if r.decision != "unavailable" and r.verified_value is not None:
            if not r.verified_value.is_finite():
                raise ValueError("Verified values must be finite.")
            values[r.field_name] = r.verified_value
    return values
