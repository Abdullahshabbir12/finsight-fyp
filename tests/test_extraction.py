from decimal import Decimal
import pytest
from src.demo import demo_run
from src.extraction.service import Candidate, checked_candidate, normalize, parse_number


@pytest.mark.parametrize("raw,unit,field,expected", [
    ("1,250", "PKR thousand", "revenue", "1250000"),
    ("(12.5)", "PKR million", "net_profit", "-12500000"),
    ("3.4", "PKR/share", "eps", "3.4"),
    ("10", "shares million", "number_of_shares", "10000000"),
    ("2", "PKR billion", "revenue", "2000000000"),
])
def test_units(raw, unit, field, expected):
    assert normalize(raw, unit, field) == Decimal(expected)


@pytest.mark.parametrize("raw", ["-", "N/A", "NaN", "1 234", "1e20", "", "1,25", "12,34,56"])
def test_ambiguous_numbers(raw):
    with pytest.raises(ValueError):
        parse_number(raw)


def test_evidence_and_year_guard():
    run = demo_run()
    item = run.fields[0]
    c = Candidate(field_name="revenue", reporting_year=2025, raw_value="1000", unit="PKR million",
                  source_page=1, source_text=item.source_text, confidence=.9, statement_basis="consolidated")
    chunk = "[PDF PAGE 1]\n" + run.pages[0].text
    assert checked_candidate(c, run, chunk).normalized_value == Decimal("1000000000")
    corrected = checked_candidate(c.model_copy(update={"source_page": 100}), run, chunk)
    assert corrected.source_page == 1 and corrected.normalized_value == Decimal("1000000000")
    for update in [{"reporting_year": 2024}, {"raw_value": "100"},
                   {"source_text": "invented 1000"}, {"unit": "USD million"}, {"statement_basis": "standalone"}]:
        result = checked_candidate(c.model_copy(update=update), run, chunk)
        assert result.normalized_value is None
        assert result.issues


def test_eps_cannot_use_statement_scale():
    with pytest.raises(ValueError):
        normalize("5", "PKR million", "eps")


def test_bracketed_expenses_are_stored_positive_with_a_visible_note():
    run = demo_run()
    chunk = "[PDF PAGE 1]\nCost of sales 28 (54,345,821)\nRevenue 80,026,226"
    run.pages[0].text = chunk
    c = Candidate(field_name="cost_of_sales", reporting_year=2025, raw_value="(54,345,821)", unit="PKR thousand",
                  source_page=1, source_text="Cost of sales 28 (54,345,821)", confidence=.9, statement_basis="consolidated")
    field = checked_candidate(c, run, chunk)
    assert field.normalized_value == Decimal("54345821000") and field.status == "extracted"
    assert field.raw_value == "(54,345,821)" and field.notes and not field.issues
    # A non-expense field keeps its sign: a negative operating cash flow is real information.
    ocf = checked_candidate(c.model_copy(update={"field_name": "operating_cash_flow"}), run, chunk)
    assert ocf.normalized_value == Decimal("-54345821000") and not ocf.notes


def test_conflicts_show_both_candidates():
    from src.extraction.service import ExtractionResponse, extract_fields
    run = demo_run()
    run.pages[0].text = "Finance cost 32 (4,128,579)"
    run.pages[1].text = "Finance cost paid (3,018,963)"
    replies = iter([("(4,128,579)", 1, "Finance cost 32 (4,128,579)"), ("(3,018,963)", 2, "Finance cost paid (3,018,963)")])
    class Fake:
        usage = []
        def request(self, *args):
            raw, page, quote = next(replies)
            return ExtractionResponse(fields=[{"field_name": "finance_cost", "reporting_year": 2025, "raw_value": raw,
                "unit": "PKR thousand", "source_page": page, "source_text": quote, "confidence": .9, "statement_basis": "consolidated"}])
    extract_fields(run, [1, 2], Fake(), second_look=False)
    field = next(f for f in run.fields if f.field_name == "finance_cost")
    assert field.status == "needs_review" and field.normalized_value is None
    assert "4,128,579" in field.issues[0] and "3,018,963" in field.issues[0] and "page 2" in field.issues[0]


def test_wrong_page_number_is_corrected_from_the_verified_quote():
    run = demo_run()
    chunk = "[PDF PAGE 2]\n" + run.pages[1].text
    item = run.fields[8]  # total assets, on synthetic page 2
    c = Candidate(field_name="total_assets", reporting_year=2025, raw_value="1500", unit="PKR million",
                  source_page=3, source_text=item.source_text, confidence=.9, statement_basis="consolidated")
    field = checked_candidate(c, run, chunk)
    assert field.source_page == 2 and field.status == "extracted" and "page 3" in field.notes[0]
    # Without a verified quote, the page is not trusted and the row stays blocked.
    invented = checked_candidate(c.model_copy(update={"source_text": "Total assets 1500 invented"}), run, chunk)
    assert invented.normalized_value is None and invented.source_page == 3



@pytest.mark.parametrize("unit,field,expected", [
    ("Rupees", "revenue", "PKR"), ("Rs.", "revenue", "PKR"), ("Rupees ('000)", "revenue", "PKR thousand"),
    ("Rupees in million", "net_profit", "PKR million"), ("Rupees", "eps", "PKR/share"),
    ("Number of shares", "number_of_shares", "shares"), ("PKR thousand", "revenue", "PKR thousand"),
])
def test_unit_spellings_are_mapped(unit, field, expected):
    from src.extraction.service import canonical_unit
    assert canonical_unit(unit, field)[0] == expected


@pytest.mark.parametrize("unit", ["US$ '000", "USD thousand", "unknown", "Rupees per share"])
def test_foreign_or_unclear_units_stay_rejected(unit):
    from src.extraction.service import canonical_unit
    assert canonical_unit(unit, "revenue")[0] == unit


def test_one_rejected_answer_does_not_stop_other_pages():
    from src.ai.client import AIOutputRejected
    from src.extraction.service import ExtractionResponse, extract_fields
    run = demo_run()
    calls = []
    class Fake:
        usage = []
        def request(self, *args):
            calls.append(1)
            if len(calls) == 1:
                raise AIOutputRejected("The model returned invalid structured JSON.")
            return ExtractionResponse(fields=[{"field_name": "total_assets", "reporting_year": 2025, "raw_value": "1500",
                "unit": "Rupees in million", "source_page": 2, "source_text": run.fields[8].source_text,
                "confidence": .9, "statement_basis": "consolidated"}])
    extract_fields(run, [1, 2], Fake(), second_look=False)
    field = next(f for f in run.fields if f.field_name == "total_assets")
    assert len(calls) == 2 and field.normalized_value == Decimal("1500000000") and field.unit == "PKR million"


def test_prior_year_fields_must_come_from_the_comparative_year():
    run = demo_run()
    item = next(f for f in run.fields if f.field_name == "revenue_prior_year")
    chunk = "[PDF PAGE 1]\n" + run.pages[0].text
    c = Candidate(field_name="revenue_prior_year", reporting_year=2024, raw_value="900", unit="PKR million",
                  source_page=1, source_text=item.source_text, confidence=.9, statement_basis="consolidated")
    assert checked_candidate(c, run, chunk).normalized_value == Decimal("900000000")
    wrong_year = checked_candidate(c.model_copy(update={"reporting_year": 2025}), run, chunk)
    assert wrong_year.normalized_value is None and "Reporting-period mismatch." in wrong_year.issues



def test_rebuilt_quote_is_replaced_by_the_real_printed_line():
    run = demo_run()
    chunk = "[PDF PAGE 1]\n2,919,376 2,557,333 Mark-up / return / profit / interest earned 25 813,192,081 712,345,078"
    run.pages[0].text = chunk
    c = Candidate(field_name="revenue", reporting_year=2025, raw_value="813,192,081", unit="PKR thousand", source_page=1,
                  source_text="813,192,081 712,345,078 Mark-up / return / profit / interest earned 25 813,192,081 712,345,078",
                  confidence=.9, statement_basis="consolidated")
    field = checked_candidate(c, run, chunk)
    assert field.status == "extracted" and field.source_text.startswith("2,919,376") and "not verbatim" in field.notes[0]
    # A label that is not on the page is still rejected.
    invented = checked_candidate(c.model_copy(update={"source_text": "Interest income 813,192,081"}), run, chunk)
    assert invented.status == "needs_review" and invented.normalized_value is None


def scripted(run, first: dict, second: dict, fail_on=None):
    """A fake model: page -> fields on the full first pass; page -> fields when asked only for missed fields."""
    from src.ai.client import AIError
    from src.extraction.service import ExtractionResponse
    demo = {f.field_name: f for f in demo_run().fields}
    class Fake:
        usage = []
        calls = []
        def request(self, schema, system, payload, stage):
            page = int(payload["evidence"].split("]")[0].split()[-1])
            again = len(payload["field_catalogue"]) < 27
            self.calls.append((page, again, list(payload["field_catalogue"])))
            if fail_on and len(self.calls) == fail_on:
                raise AIError("Daily quota reached")
            keys = (second if again else first).get(page, [])
            return ExtractionResponse(fields=[{"field_name": k, "reporting_year": demo[k].reporting_year,
                "raw_value": demo[k].raw_value, "unit": demo[k].unit, "source_page": page, "source_text": demo[k].source_text,
                "confidence": .9, "statement_basis": "consolidated"} for k in keys])
    return Fake()


def test_second_look_asks_only_for_missed_fields_on_the_best_pages():
    from src.extraction.service import extract_fields
    run = demo_run()
    fake = scripted(run, first={1: ["revenue", "cost_of_sales", "gross_profit"], 2: ["total_assets"]},
                    second={1: ["net_profit", "revenue"], 2: ["equity"]})
    extract_fields(run, [1, 2, 3], fake)
    assert [(page, again) for page, again, _ in fake.calls] == [(1, False), (2, False), (3, False), (1, True), (2, True), (3, True)]
    asked = fake.calls[3][2]
    assert "net_profit" in asked and "revenue" not in asked and len(asked) == 23   # only the 23 missed fields
    fields = {f.field_name: f for f in run.fields}
    assert fields["net_profit"].normalized_value == 105000000 and "second look" in fields["net_profit"].notes[-1]
    assert fields["equity"].status == "extracted" and fields["revenue"].normalized_value == 1000000000
    assert any("Second look: asked again for 23 missing fields on PDF pages 1, 2, 3; 2 found." == w for w in run.warnings)


def test_no_second_look_after_a_quota_failure_or_when_nothing_is_missing():
    from src.extraction.service import extract_fields
    run = demo_run()
    fake = scripted(run, first={1: ["revenue"]}, second={1: ["net_profit"]}, fail_on=2)
    extract_fields(run, [1, 2, 3], fake)
    assert len(fake.calls) == 2 and not any("Second look" in w for w in run.warnings)
    run = demo_run()
    everything = {p: [f.field_name for f in demo_run().fields if f.source_page == p] for p in (1, 2, 3)}
    fake = scripted(run, first=everything, second={})
    extract_fields(run, [1, 2, 3], fake)
    assert len(fake.calls) == 3 and all(f.status == "extracted" for f in run.fields)


def test_second_look_prefers_productive_pages_then_empty_ones_up_to_six():
    from src.extraction.service import SECOND_LOOK_PAGES, second_look_pages
    from src.models import FinancialField
    found = {f"k{i}": FinancialField(field_name="revenue", source_page=page) for i, page in
             enumerate([5, 5, 5, 6, 6, 7, 8, 9, 9, 9, 9, 40])}
    assert SECOND_LOOK_PAGES == 6
    assert second_look_pages(found, [4, 5, 6, 7, 8, 9]) == [4, 5, 6, 7, 8, 9]      # a page that yielded nothing is re-read
    assert second_look_pages(found, [1, 2, 3, 5, 6, 7, 8, 9]) == [1, 5, 6, 7, 8, 9]  # capped: productive pages first


def test_second_look_is_not_spent_on_fields_never_printed_as_one_figure():
    from src.extraction.service import ExtractionResponse, extract_fields
    from tests.test_bank import bank_run
    run = bank_run()
    run.verified_at, run.reviews = None, []
    for page_number in (1, 2):
        run.pages.append(run.pages[0].model_copy(update={"number": page_number + 1}))
    calls = []
    class Fake:
        usage = []
        def request(self, schema, system, payload, stage):
            calls.append(payload["field_catalogue"])
            page = int(payload["evidence"].split("]")[0].split()[-1])
            keys = [k for k in payload["field_catalogue"] if k != "casa_deposits"] if page == 1 else []
            return ExtractionResponse(fields=[{"field_name": k, "reporting_year": 2023 if k.endswith("_prior_year") else 2024,
                "raw_value": next(f.raw_value for f in bank_run().fields if f.field_name == k), "unit": "PKR",
                "source_page": 1, "source_text": next(f.source_text for f in bank_run().fields if f.field_name == k),
                "confidence": .9, "statement_basis": "consolidated"} for k in keys])
    for page in run.pages:
        page.text = "\n".join(f.source_text for f in bank_run().fields)
    extract_fields(run, [1, 2, 3], Fake())
    assert len(calls) == 3 and not any("Second look" in w for w in run.warnings)   # only CASA missing: no extra requests
