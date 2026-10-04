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
    for update in [{"reporting_year": 2024}, {"source_page": 100}, {"raw_value": "100"},
                   {"source_text": "invented 1000"}, {"unit": "USD million"}, {"statement_basis": "standalone"}]:
        result = checked_candidate(c.model_copy(update=update), run, chunk)
        assert result.normalized_value is None
        assert result.issues


def test_eps_cannot_use_statement_scale():
    with pytest.raises(ValueError):
        normalize("5", "PKR million", "eps")
