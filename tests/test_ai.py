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


def test_reference_ids_in_prose_are_rendered_and_counted_as_evidence():
    from src.ai.council import render_text
    run = reviewed_demo()
    run_council(run)
    registry = reference_registry(run)
    claim = Claim(kind="FACT", text="Net profit was field:net_profit, a margin of metric:net_profit_margin.")
    validate_claim(claim, registry)
    assert claim.references == ["field:net_profit", "metric:net_profit_margin"]
    assert render_text(claim.text, registry) == "Net profit was PKR 105.00 million, a margin of 10.50%."
    with pytest.raises(AIError, match="unknown"):
        validate_claim(Claim(kind="FACT", text="Value was field:invented."), registry)


@pytest.mark.parametrize("text", [
    "Total liabilities exceed total assets.",
    "Total liabilities of field:total_liabilities exceeded total assets of field:total_assets.",
    "The company reported negative operating cash flow.",
    "Net profit was negative in the reporting period.",
    "The current ratio of metric:current_ratio is below one.",
    "Current assets are not sufficient to cover current liabilities.",
])
def test_statements_contradicting_verified_values_are_rejected(text):
    run = reviewed_demo()
    run_council(run)
    with pytest.raises(AIError, match="contradicts"):
        validate_claim(Claim(kind="INTERPRETATION", text=text, references=["field:total_assets"]), reference_registry(run))


@pytest.mark.parametrize("text", [
    "Total liabilities are below total assets.",
    "Total assets exceed total liabilities.",
    "Operating cash flow exceeds net profit.",
    "The company reported positive operating cash flow and a positive net profit margin.",
    "The current ratio is above one.",
    "Total liabilities do not exceed total assets.",
])
def test_statements_consistent_with_verified_values_pass(text):
    run = reviewed_demo()
    run_council(run)
    validate_claim(Claim(kind="INTERPRETATION", text=text, references=["field:total_assets"]), reference_registry(run))


def test_evaluative_words_need_benchmarks():
    run = reviewed_demo()
    run_council(run)
    claim = Claim(kind="INTERPRETATION", text="Profitability is strong.", references=["metric:net_profit_margin"])
    with pytest.raises(AIError, match="evaluative"):
        validate_claim(claim, reference_registry(run))
    validate_claim(Claim(kind="LIMITATION", text="Without benchmarks we cannot call margins strong."), reference_registry(run))
    run.company.benchmarks = "Peer net margin, FY2025, source: user"
    validate_claim(claim, reference_registry(run))


def test_bank_guidance_only_for_banks():
    from src.ai.council import policy
    run = reviewed_demo()
    assert "deposit" not in policy(run)
    run.company.industry = "Commercial banking"
    assert "deposit" in policy(run)


def test_comparisons_are_supplied_to_the_ai():
    run = reviewed_demo()
    facts = analysis_payload(run)["verified_comparisons"]
    assert "Total Liabilities is LESS than Total Assets." in facts
    assert "Current Ratio is ABOVE one." in facts


def test_rejected_output_is_retried_with_the_reason():
    from src.ai.council import demo_analyst
    from src.models import AnalystOutput
    run = reviewed_demo()
    run.is_demo = False
    seen = []
    class Fake:
        usage = []
        def request(self, schema, system, payload, stage):
            seen.append(payload.get("previous_attempts_rejected_because"))
            good = demo_analyst(run, stage)
            if len(seen) == 1:
                bad = good.model_copy(deep=True)
                bad.overall_observation = Claim(kind="INTERPRETATION", text="Total liabilities exceed total assets.", references=["field:total_assets"])
                return bad
            return good
    run_council(run, Fake())
    assert len(run.analysts) == 4 and len(seen) == 5
    assert seen[0] is None and "contradicts" in seen[1][0]


def test_retries_stop_after_three_rejections():
    from src.ai.client import AIOutputRejected
    run = reviewed_demo()
    run.is_demo = False
    class Fake:
        usage = []
        calls = 0
        def request(self, *args):
            self.calls += 1
            raise AIOutputRejected("The model returned invalid structured JSON.")
    client = Fake()
    with pytest.raises(AIError, match="3 automatic attempts"):
        run_council(run, client)
    assert client.calls == 3 and not run.analysts



@pytest.mark.parametrize("text", ["A margin of metric:.", "Compare net:net_profit with cash flow.", "Margin was metric:gross_margin."])
def test_malformed_reference_ids_are_rejected(text):
    run = reviewed_demo()
    run_council(run)
    with pytest.raises(AIError):
        validate_claim(Claim(kind="INTERPRETATION", text=text, references=["field:revenue"]), reference_registry(run))
    # Ordinary colons in prose remain allowed.
    validate_claim(Claim(kind="LIMITATION", text="Note: single-year data only."), reference_registry(run))


def test_growth_direction_is_checked_and_trends_need_prior_year_data():
    run = reviewed_demo()
    run_council(run)
    registry = reference_registry(run)
    validate_claim(Claim(kind="FACT", text="Revenue increased by metric:revenue_growth."), registry)
    for text in ("Operating cash flow increased during the reporting period.", "Revenue declined year on year."):
        with pytest.raises(AIError, match="contradicts"):
            validate_claim(Claim(kind="FACT", text=text, references=["field:revenue"]), registry)
    assert "Revenue / Sales INCREASED versus the prior year." in analysis_payload(run)["verified_comparisons"]
    review = next(r for r in run.reviews if r.field_name == "revenue_prior_year")
    review.decision, review.verified_value = "unavailable", None
    run_council_registry = reference_registry(run.model_copy(update={"metrics": [m for m in run.metrics if m.name != "revenue_growth"]}))
    with pytest.raises(AIError, match="without verified prior-year data"):
        validate_claim(Claim(kind="FACT", text="Revenue increased.", references=["field:revenue"]), run_council_registry)
