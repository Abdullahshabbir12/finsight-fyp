"""Small, serializable records. Extracted and reviewed values remain separate."""
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.catalog import FIELDS, expected_year


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Company(Record):
    name: str = Field(min_length=1, max_length=200)
    ticker: str = ""
    industry: str = ""
    financial_year: int = Field(ge=1900, le=2200)
    statement_basis: Literal["consolidated", "standalone"] = "consolidated"
    benchmarks: str = Field(default="", max_length=4000)


class Page(Record):
    number: int = Field(ge=1)
    text: str


class FinancialField(Record):
    field_name: str
    reporting_year: int | None = None
    raw_value: str | None = None
    normalized_value: Decimal | None = None
    unit: str = "unknown"
    source_page: int | None = None
    source_text: str = ""
    confidence: float = Field(default=0, ge=0, le=1)
    status: Literal["extracted", "missing", "needs_review"] = "missing"
    issues: list[str] = Field(default_factory=list)
    # Informational conventions applied by Python (e.g. expense sign); unlike issues, they never block acceptance.
    notes: list[str] = Field(default_factory=list)

    @field_validator("field_name")
    @classmethod
    def known_field(cls, value: str) -> str:
        if value not in FIELDS:
            raise ValueError("Unknown financial field")
        return value


class Review(Record):
    field_name: str
    decision: Literal["accept", "edit", "unavailable"]
    verified_value: Decimal | None
    reporting_year: int
    source_page: int | None = None
    source_text: str = ""
    note: str = ""
    reason: str = ""  # chosen from a fixed list in the review table, so corrections can be counted by type

    def explanation(self) -> str:
        return " — ".join(part for part in (self.reason, self.note) if part)


class Metric(Record):
    name: str
    label: str
    value: Decimal | None
    format: Literal["percent", "multiple"]
    formula: str
    inputs: list[str]
    reason: str = ""


class Claim(Record):
    kind: Literal["FACT", "INTERPRETATION", "LIMITATION"]
    text: str = Field(min_length=1, max_length=1500)
    references: list[str] = Field(default_factory=list)


class AnalystOutput(Record):
    analyst_name: str
    overall_observation: Claim
    positive_factors: list[Claim]
    risk_factors: list[Claim]
    key_metrics: list[str]
    evidence: list[str]
    limitations: list[Claim]


class Section(Record):
    heading: str
    claims: list[Claim]


class Synthesis(Record):
    sections: list[Section]


class Run(Record):
    id: str
    company: Company
    is_demo: bool = False
    filename: str = ""
    source: str = ""  # where the PDF came from, e.g. the PSX financial reports library document
    pages: list[Page] = Field(default_factory=list)
    fields: list[FinancialField] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    analysts: dict[str, AnalystOutput] = Field(default_factory=dict)
    synthesis: Synthesis | None = None
    warnings: list[str] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)
    usage: list[dict] = Field(default_factory=list)
    extraction_attempts: int = 0
    created_at: str
    verified_at: str | None = None
    analysis_seconds: float = 0
    # Unfinished review decisions ("Save progress"); cleared when verification is finished.
    review_draft: list[dict] = Field(default_factory=list)


def upgrade_run(run: Run) -> Run:
    """Add fields introduced after a run was saved, so older runs still open and calculate.

    A verified run gets an 'unavailable' review for each new field; nothing is invented.
    """
    present = {f.field_name for f in run.fields}
    for key in FIELDS:
        if key not in present:
            run.fields.append(FinancialField(field_name=key))
    run.fields.sort(key=lambda f: list(FIELDS).index(f.field_name))
    if run.verified_at:
        reviewed = {r.field_name for r in run.reviews}
        for key in FIELDS:
            if key not in reviewed:
                run.reviews.append(Review(field_name=key, decision="unavailable", verified_value=None,
                                          reporting_year=expected_year(key, run.company.financial_year),
                                          note="Field added to FinSight after this run was verified; not captured."))
        run.reviews.sort(key=lambda r: list(FIELDS).index(r.field_name))
    return run
