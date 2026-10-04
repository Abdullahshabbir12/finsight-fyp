"""Transparent academic evaluation; human review is the reference, not an audit."""
from src.catalog import FIELDS
from src.models import Run


def evaluation(run: Run) -> dict:
    fields = {f.field_name: f for f in run.fields}
    verifiable = [r for r in run.reviews if r.decision != "unavailable" and r.verified_value is not None]
    correct = sum(fields[r.field_name].normalized_value == r.verified_value and
                  fields[r.field_name].reporting_year == r.reporting_year for r in verifiable)
    extracted = sum(f.normalized_value is not None for f in run.fields)
    reviewed = len(run.reviews)
    costs = [u["cost"] for u in run.usage if isinstance(u.get("cost"), (int, float))]
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
