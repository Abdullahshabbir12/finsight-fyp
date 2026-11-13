"""Small, serializable records. Extracted and reviewed values remain separate."""
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.catalog import LABELS, catalog, expected_year


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Company(Record):
    name: str = Field(min_length=1, max_length=200)
    ticker: str = ""
    industry: str = ""
    financial_year: int = Field(ge=1900, le=2200)
    statement_basis: Literal["consolidated", "standalone"] = "consolidated"
    sector: Literal["general", "bank"] = "general"  # chooses the field catalogue and ratios
    benchmarks: str = Field(default="", max_length=4000)
    # Market inputs typed by the user, never extracted or verified. Kept away from the AI (see profile()).
    share_price: Decimal | None = Field(default=None, gt=0)
    price_date: str = Field(default="", max_length=40)
    dividend_per_share: Decimal | None = Field(default=None, ge=0)

    def profile(self) -> dict:
        """Company details for AI prompts, without the user's market inputs, so valuation never enters the analysis."""
        return self.model_dump(exclude={"share_price", "price_date", "dividend_per_share"})


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
        if value not in LABELS:
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
    format: Literal["percent", "multiple", "amount"]
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


class Finding(Record):
    """A check result an analyst can act on: what was found, the figures behind it, and what to look at next."""
    key: str  # stable across recalculation, so an analyst's decision stays attached to it
    category: str
    priority: Literal["high", "medium", "low"]
    title: str
    detail: str
    fields: list[str] = Field(default_factory=list)  # verified fields involved; each can be shown on its PDF page
    calculation: str = ""
    why: str = ""
    next_steps: list[str] = Field(default_factory=list)


class FindingDecision(Record):
    """One analyst decision on a finding. The list per finding is its history; the last entry is current."""
    status: Literal["confirmed", "investigating", "dismissed"]
    comment: str = Field(default="", max_length=2000)
    detail: str  # the finding as it read when decided, to show when later figures change it
    at: str


class ModelAssumptions(Record):
    """The analyst's assumptions for the financial model. Rates are fractions (0.075 = 7.5%); amounts are PKR.

    BrokerLens pre-fills them from verified figures, but they belong to the analyst; None means not set yet.
    """
    sales_growth: Decimal | None = Field(default=None, gt=-1, lt=5)
    gross_margin: Decimal | None = Field(default=None, gt=-1, lt=1)
    operating_costs: Decimal | None = Field(default=None, gt=-1, lt=5)  # share of sales, net of other income
    finance_cost: Decimal | None = Field(default=None, ge=0)            # PKR a year
    tax_rate: Decimal | None = Field(default=None, ge=0, lt=1)
    capex: Decimal | None = Field(default=None, ge=0, lt=5)             # share of sales
    depreciation: Decimal | None = Field(default=None, ge=0, lt=5)      # share of sales; typed by the analyst
    working_capital: Decimal | None = Field(default=None, ge=0, lt=5)   # receivables + inventory, share of sales
    discount_rate: Decimal | None = Field(default=None, gt=0, lt=1)
    terminal_growth: Decimal | None = Field(default=None, gt=-1, lt=1)
    net_debt: Decimal | None = None                                     # PKR; negative means net cash
    # Scenarios: shifts applied to the base case, in fractions (-0.03 = three percentage points lower).
    downside_growth: Decimal = Field(default=Decimal("-0.03"), gt=-1, lt=1)
    downside_margin: Decimal = Field(default=Decimal("-0.02"), gt=-1, lt=1)
    upside_growth: Decimal = Field(default=Decimal("0.03"), gt=-1, lt=1)
    upside_margin: Decimal = Field(default=Decimal("0.02"), gt=-1, lt=1)
    # Input-cost shock: the share of cost of sales exposed to one commodity, and that commodity's price change.
    shock_share: Decimal = Field(default=Decimal(0), ge=0, le=1)
    shock_change: Decimal = Field(default=Decimal(0), ge=-1, le=5)
    in_report: bool = False  # the analyst chose to put this model in the downloaded report


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
    finding_decisions: dict[str, list[FindingDecision]] = Field(default_factory=dict)
    # Financial model assumptions. Like the share price, never sent to the AI analysts.
    model_assumptions: ModelAssumptions | None = None


def upgrade_run(run: Run) -> Run:
    """Add fields introduced after a run was saved, so older runs still open and calculate.

    A verified run gets an 'unavailable' review for each new field; nothing is invented.
    """
    fields = list(catalog(run.company.sector))
    present = {f.field_name for f in run.fields}
    for key in fields:
        if key not in present:
            run.fields.append(FinancialField(field_name=key))
    run.fields.sort(key=lambda f: fields.index(f.field_name))
    if run.verified_at:
        reviewed = {r.field_name for r in run.reviews}
        for key in fields:
            if key not in reviewed:
                run.reviews.append(Review(field_name=key, decision="unavailable", verified_value=None,
                                          reporting_year=expected_year(key, run.company.financial_year),
                                          note="Field added to BrokerLens after this run was verified; not captured."))
        run.reviews.sort(key=lambda r: fields.index(r.field_name))
    return run
