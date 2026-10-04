"""Transparent academic evaluation; human review is the reference, not an audit."""
from decimal import Decimal
from src.catalog import FIELDS
from src.extraction.service import apply_expense_convention, normalize
from src.models import FinancialField, Run

# Per-field outcome of AI extraction, judged against the saved human review.
OUTCOMES = {
    "correct": "AI value accepted unchanged",
    "correct_but_flagged": "AI proposed the right number, but a check flagged it (e.g. conflicting pages)",
    "sign_corrected": "Right amount, opposite sign",
    "wrong_year": "Right number from the wrong reporting year",
    "wrong_value": "AI proposed a different number",
    "filled_by_human": "AI returned no value; the reviewer supplied one",
    "unavailable": "Reviewer marked the field unavailable",
    "pending": "Not reviewed yet",
}


def proposed_value(field: FinancialField) -> Decimal | None:
    """The number the AI proposed, even when a check later blocked it."""
    if field.normalized_value is not None:
        return field.normalized_value
    if field.raw_value is None:
        return None
    try:
        return apply_expense_convention(field.field_name, normalize(field.raw_value, field.unit, field.field_name))[0]
    except ValueError:
        return None


def field_outcomes(run: Run) -> list[dict]:
    reviews = {r.field_name: r for r in run.reviews}
    rows = []
    for f in run.fields:
        r = reviews.get(f.field_name)
        proposed = proposed_value(f)
        if r is None:
            outcome = "pending"
        elif r.decision == "unavailable" or r.verified_value is None:
            outcome = "unavailable"
        elif proposed is None:
            outcome = "filled_by_human"
        elif proposed == r.verified_value:
            if f.reporting_year not in (None, r.reporting_year):
                outcome = "wrong_year"
            else:
                outcome = "correct" if r.decision == "accept" else "correct_but_flagged"
        elif proposed == -r.verified_value:
            outcome = "sign_corrected"
        else:
            outcome = "wrong_value"
        rows.append({"field": f.field_name, "label": FIELDS[f.field_name], "outcome": outcome,
                     "ai_proposed": None if proposed is None else str(proposed),
                     "verified": None if r is None or r.verified_value is None else str(r.verified_value),
                     "extraction_status": f.status, "review_reason": r.reason if r else "", "review_note": r.note if r else ""})
    return rows


def evaluation(run: Run) -> dict:
    fields = {f.field_name: f for f in run.fields}
    verifiable = [r for r in run.reviews if r.decision != "unavailable" and r.verified_value is not None]
    correct = sum(fields[r.field_name].normalized_value == r.verified_value and
                  fields[r.field_name].reporting_year == r.reporting_year for r in verifiable)
    extracted = sum(f.normalized_value is not None for f in run.fields)
    reviewed = len(run.reviews)
    costs = [u["cost"] for u in run.usage if isinstance(u.get("cost"), (int, float))]
    outcomes = [row["outcome"] for row in field_outcomes(run)]
    count = {name: outcomes.count(name) for name in OUTCOMES}
    # Numbers the AI proposed that could be checked against a final human value.
    proposed_checked = sum(count[k] for k in ("correct", "correct_but_flagged", "sign_corrected", "wrong_year", "wrong_value"))
    right_number = count["correct"] + count["correct_but_flagged"]
    return {
        "mode": "DEMO / SYNTHETIC DATA" if run.is_demo else "Live report",
        "predefined_fields": len(FIELDS), "extracted_fields": extracted,
        "fields_accepted_without_changes": sum(r.decision == "accept" for r in run.reviews),
        "fields_edited_by_user": sum(r.decision == "edit" for r in run.reviews),
        "numeric_or_year_correction_count": len(verifiable) - correct,
        "unavailable_fields": sum(r.decision == "unavailable" for r in run.reviews),
        "pending_review_fields": len(FIELDS) - reviewed,
        "fields_that_could_be_verified": len(verifiable), "correctly_extracted_fields": correct,
        "extraction_accuracy": correct / len(verifiable) if verifiable else None,
        "extraction_completeness": extracted / len(FIELDS),
        "verified_coverage": len(verifiable) / len(FIELDS),
        # Precision: of the numbers the AI proposed, how many were right. Recall: of the verified fields, how many it found.
        "proposal_precision": right_number / proposed_checked if proposed_checked else None,
        "field_recall": right_number / len(verifiable) if verifiable else None,
        **{f"outcome_{name}": count[name] for name in OUTCOMES},
        "pdf_processing_seconds": run.timings.get("pdf_seconds", 0),
        "ai_extraction_seconds": run.timings.get("extraction_seconds", 0),
        "ai_analysis_seconds": run.analysis_seconds,
        "total_processing_seconds": run.timings.get("pdf_seconds", 0) + run.timings.get("extraction_seconds", 0) + run.analysis_seconds,
        "observed_workflow_seconds": run.timings.get("workflow_seconds"),
        "extraction_attempts": run.extraction_attempts,
        "api_calls": len(run.usage), "api_successes": sum(u.get("success", False) for u in run.usage),
        "reported_prompt_tokens": sum(u.get("prompt_tokens") or 0 for u in run.usage) if any(u.get("prompt_tokens") is not None for u in run.usage) else None,
        "reported_completion_tokens": sum(u.get("completion_tokens") or 0 for u in run.usage) if any(u.get("completion_tokens") is not None for u in run.usage) else None,
        "reported_cost_subtotal": sum(costs) if costs else None,
        "calls_without_reported_cost": len(run.usage) - len(costs),
    }


def aggregate(runs: list[Run]) -> tuple[list[dict], list[dict]]:
    """Combine reviewed live runs: one summary row per run, and outcome counts per field across runs."""
    summaries, per_field = [], {k: {name: 0 for name in OUTCOMES} for k in FIELDS}
    for run in runs:
        if run.is_demo or not run.verified_at:
            continue
        stats = evaluation(run)
        summaries.append({"company": run.company.name, "year": run.company.financial_year, "run_id": run.id,
                          **{k: stats[k] for k in ("proposal_precision", "field_recall", "extraction_accuracy",
                                                   "extraction_completeness", "fields_edited_by_user", "unavailable_fields",
                                                   "ai_extraction_seconds", "total_processing_seconds", "api_calls")},
                          **{k: v for k, v in stats.items() if k.startswith("outcome_")}})
        for row in field_outcomes(run):
            per_field[row["field"]][row["outcome"]] += 1
    fields = [{"field": FIELDS[k], **counts} for k, counts in per_field.items()] if summaries else []
    return summaries, fields
