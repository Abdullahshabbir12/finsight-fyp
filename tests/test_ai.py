import pytest
from src.ai.client import AIError
from src.ai.council import analysis_payload, reference_registry, run_council, validate_claim
from src.models import Claim
from tests.test_validation import reviewed_demo


def test_demo_council_uses_verified_data_and_four_roles():
    run = reviewed_demo()
    run_council(run)
    assert len(run.analysts) == 4
    assert "Insufficient benchmark" in run.analysts["Industry Analyst"].overall_observation.text
    payload = analysis_payload(run)
    assert "fields" not in payload and "raw_value" not in str(payload)
    assert payload["reference_registry"]["field:revenue"]["value"] == "1000000000"


@pytest.mark.parametrize("claim", [
    Claim(kind="FACT", text="Revenue is 9999.", references=["field:revenue"]),
    Claim(kind="INTERPRETATION", text="Buy this stock.", references=["field:revenue"]),
    Claim(kind="FACT", text="Profitability is strong.", references=["metric:invented"]),
    Claim(kind="FACT", text="The company has positive earnings."),
    Claim(kind="FACT", text="This company committed fraud.", references=["field:revenue"]),
])
def test_invalid_claims_rejected(claim):
    run = reviewed_demo()
    with pytest.raises(AIError):
        validate_claim(claim, reference_registry(run))


def test_council_requires_verification():
    from src.demo import demo_run
    with pytest.raises(ValueError):
        run_council(demo_run())


def test_unavailable_review_reasons_reach_ai_without_extracted_values():
    run = reviewed_demo()
    review = next(r for r in run.reviews if r.field_name == "total_debt")
    review.decision = "unavailable"
    review.verified_value = None
    review.note = "Borrowings alone do not establish aggregate debt."
    payload = analysis_payload(run)
    assert {"field_name": "total_debt", "reason": review.note} in payload["unavailable_fields"]
    assert "field:total_debt" not in payload["reference_registry"]


def test_synthesis_requires_all_roles_and_has_eleven_sections():
    from src.ai.synthesis import HEADINGS, run_synthesis
    run = reviewed_demo()
    with pytest.raises(AIError, match="four"):
        run_synthesis(run)
    run_council(run)
    run_synthesis(run)
    assert [s.heading for s in run.synthesis.sections] == HEADINGS
