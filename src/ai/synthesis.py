"""A neutral synthesis over all four validated perspectives."""
from time import perf_counter
from src.ai.client import AIClient, AIError, AIOutputRejected
from src.ai.council import ROLES, analysis_payload, policy, request_validated, validate_claim
from src.models import Claim, Run, Section, Synthesis

HEADINGS = ["Executive Summary", "Profitability Assessment", "Liquidity and Credit Risk",
            "Cash Flow Assessment", "Financial Quality / Warning Indicators", "Industry Context",
            "Major Strengths", "Major Risks", "Information Gaps", "Areas Requiring Human Review",
            "Final Neutral Conclusion"]


def validate_synthesis(result: Synthesis, registry: dict) -> None:
    if [s.heading for s in result.sections] != HEADINGS:
        raise AIOutputRejected("Synthesis must contain exactly the required section headings, in order. Retry synthesis.")
    for section in result.sections:
        if not section.claims:
            raise AIOutputRejected(f"Synthesis section '{section.heading}' was empty. Retry synthesis.")
        for claim in section.claims:
            validate_claim(claim, registry)


def demo_synthesis(run: Run, registry: dict) -> Synthesis:
    fund = run.analysts["Fundamental Analyst"]
    credit = run.analysts["Credit Risk Analyst"]
    quality = run.analysts["Forensic Analyst"]
    industry = run.analysts["Industry Analyst"]
    limitation = lambda text: Claim(kind="LIMITATION", text=text)
    available = lambda refs: [r for r in refs if r in registry]
    refs = available(["field:revenue", "field:net_profit", "metric:current_ratio"])
    summary = Claim(kind="INTERPRETATION" if refs else "LIMITATION", text="This synthetic research summary brings together verified financial data, deterministic metrics and focused analyst perspectives for human review.", references=refs)
    cash_refs = available(["field:operating_cash_flow", "metric:operating_cash_flow_to_debt", "metric:operating_cash_flow_margin"])
    cash = Claim(kind="INTERPRETATION" if cash_refs else "LIMITATION", text="Review cash generation alongside earnings and debt service needs; timing, working capital and noncash items require the underlying notes.", references=cash_refs)
    strengths = [c for a in run.analysts.values() for c in a.positive_factors]
    risks = [c for a in run.analysts.values() for c in a.risk_factors]
    claims = [[summary], [fund.overall_observation, *fund.positive_factors], [credit.overall_observation, *credit.risk_factors],
              [cash], [quality.overall_observation, *quality.risk_factors], [industry.overall_observation],
              strengths or [limitation("The available sample outputs do not establish specific strengths.")],
              risks or [limitation("Absence of a flagged issue does not establish the absence of risk.")],
              [limitation("Single-year data cannot establish financial trends. Benchmarks and accounting notes may be incomplete.")],
              [limitation("Confirm source units, reporting period, statement basis, adjustments and reconciliation warnings before using this report.")],
              [limitation("This decision-support summary is a starting point for an analyst's review. Professional judgment and additional evidence are required for any investment decision.")]]
    return Synthesis(sections=[Section(heading=h, claims=c) for h, c in zip(HEADINGS, claims)])


def run_synthesis(run: Run, client: AIClient | None = None) -> None:
    if set(run.analysts) != set(ROLES):
        raise AIError("Complete all four analyst perspectives before synthesis.")
    payload = analysis_payload(run)
    payload["analysts"] = {k: v.model_dump() for k, v in run.analysts.items()}
    payload["required_section_headings_in_order"] = HEADINGS
    start = perf_counter()
    try:
        if run.is_demo:
            result = demo_synthesis(run, payload["reference_registry"])
        else:
            if client is None:
                raise AIError("Configure an API key before requesting synthesis.")
            result = request_validated(client, Synthesis, policy(run) + "\nSynthesize all four perspectives into exactly the supplied sections. Acknowledge disagreements and missing evidence. Remain neutral.",
                                       payload, "synthesis", lambda r: validate_synthesis(r, payload["reference_registry"]))
        validate_synthesis(result, payload["reference_registry"])
        run.synthesis = result
    finally:
        elapsed = perf_counter() - start
        run.timings["synthesis_seconds"] = run.timings.get("synthesis_seconds", 0) + elapsed
        run.analysis_seconds += elapsed
        if client:
            run.usage.extend(client.usage)
            client.usage.clear()
