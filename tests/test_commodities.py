"""Commodity context: World Bank monthly prices over a company's financial year."""
import pytest
from src.market.commodities import (SECTORS, financial_year_prices, guess_sector, latest_month, prices, source_note,
                                    window, year_end_month)
from src.models import Page
from tests.test_validation import reviewed_demo


def test_snapshot_has_every_sector_series_with_a_credited_source():
    data = prices()
    assert {s for _, series in SECTORS.values() for s in series} <= set(data)
    assert "CC BY 4.0" in source_note() and "World Bank" in source_note()
    assert latest_month() >= "2026-01" and all(len(item["months"]) > 100 for item in data.values())


def test_financial_year_window_crosses_calendar_years():
    assert window(2025, 6) == [f"2024-{m:02d}" for m in range(7, 13)] + [f"2025-{m:02d}" for m in range(1, 7)]
    assert window(2024, 12)[0] == "2024-01" and window(2024, 1, 2) == ["2023-12", "2024-01"]


def test_averages_and_change_are_plain_arithmetic():
    item = financial_year_prices("Crude oil, Brent", 2024, 12)
    months = prices()["Crude oil, Brent"]["months"]
    assert item.average == pytest.approx(sum(months[f"2024-{m:02d}"] for m in range(1, 13)) / 12)
    assert item.prior_average == pytest.approx(sum(months[f"2023-{m:02d}"] for m in range(1, 13)) / 12)
    assert item.change == pytest.approx(item.average / item.prior_average - 1) and len(item.months) == 24
    assert financial_year_prices("Crude oil, Brent", 2099, 12) is None          # not covered: no partial averages
    assert financial_year_prices("Unobtainium", 2024, 12) is None


@pytest.mark.parametrize("industry,sector", [("Cement", "Cement"), ("Fertilizer", "Fertiliser"), ("Textile composite", "Textiles"),
                                             ("Oil marketing", "Refinery and oil marketing"), ("Pharmaceuticals", None)])
def test_sector_is_guessed_from_the_industry(industry, sector):
    assert guess_sector(industry) == sector


def test_year_end_is_read_from_statement_dates_even_when_glued():
    run = reviewed_demo()
    run.company.financial_year = 2025
    run.pages = [Page(number=1, text="STATEMENT OF FINANCIAL POSITIONAS AT JUNE 30, 2025\nTotal assets 1,500"),
                 Page(number=2, text="Statement of profit or loss for the year ended 30 June 2025"),
                 Page(number=3, text="Comparative figures as at December 31, 2024")]
    for review in run.reviews:
        review.source_page = 1
    assert year_end_month(run) == 6
    run.pages = [Page(number=1, text="no dates here"), Page(number=2, text="no dates either")]
    assert year_end_month(run) is None
