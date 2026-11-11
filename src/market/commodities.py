"""Commodity price context from the World Bank's monthly Pink Sheet (CC BY 4.0).

External context only: prices are not verified by BrokerLens, are in US dollars (no rupee conversion), and are never
used in the verified ratios or sent to the AI analysts.
"""
import calendar
import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from src.models import Run

DATA = Path(__file__).resolve().parent / "commodity_prices.csv"
SOURCE = Path(__file__).resolve().parent / "commodity_prices.txt"
# Sector -> (words that identify it in the company's industry, the inputs or outputs that move its margins).
SECTORS = {
    "Cement": (("cement",), ["Coal, South African", "Coal, Australian"]),
    "Fertiliser": (("fertili", "urea"), ["Urea", "DAP"]),
    "Oil and gas exploration": (("exploration", "e&p"), ["Crude oil, Brent"]),
    "Refinery and oil marketing": (("refin", "oil marketing", "petroleum", "omc"), ["Crude oil, Brent"]),
    "Power generation": (("power", "energy", "ipp"), ["Coal, Australian", "Liquefied natural gas, Japan", "Crude oil, Brent"]),
    "Textiles": (("textile", "spinning", "weaving", "composite", "apparel"), ["Cotton, A Index"]),
    "Steel and engineering": (("steel", "engineering", "iron"), ["Iron ore, cfr spot"]),
    "Sugar": (("sugar",), ["Sugar, world"]),
    "Food and edible oil": (("food", "edible", "ghee", "vanaspati", "flour"), ["Palm oil", "Soybean oil", "Wheat, US HRW"]),
    "Cables and electrical": (("cable", "electrical", "wire"), ["Copper", "Aluminum"]),
}
WHY = {
    "Cement": "Coal is the main kiln fuel; Pakistani plants import much of it, largely from South Africa.",
    "Fertiliser": "Urea and DAP are the products themselves; local urea uses regulated domestic gas, so international "
                  "prices mainly affect imported DAP and import parity.",
    "Oil and gas exploration": "Oil and gas sale prices are linked to international crude prices.",
    "Refinery and oil marketing": "Crude and product prices drive inventory gains or losses and working capital.",
    "Power generation": "Imported coal, LNG and furnace oil are fuel costs, largely passed through under tariff terms.",
    "Textiles": "Cotton is the main raw material for spinning.",
    "Steel and engineering": "Iron ore drives steel input costs; scrap, a key local input, is not in this data.",
    "Sugar": "World sugar prices set export and import parity.",
    "Food and edible oil": "Palm and soybean oil are imported raw materials; wheat drives flour and food costs.",
    "Cables and electrical": "Copper and aluminium are the main conductor materials.",
}
MONTH_NAMES = "|".join(m.lower() for m in calendar.month_name if m)
# No leading word boundary: extracted titles are sometimes glued, e.g. "POSITIONAS AT DECEMBER 31".
YEAR_END = re.compile(rf"(?:as\s+(?:at|on)|(?:year|period)\s+ended(?:\s+on)?)\s+(?:(\d{{1,2}})\s+)?({MONTH_NAMES})\s*(\d{{1,2}})?\s*,?\s*(\d{{4}})", re.I)


@dataclass(frozen=True)
class CommodityYear:
    series: str
    unit: str
    average: float
    prior_average: float | None
    change: float | None  # fraction, e.g. 0.12 for +12%
    months: list[tuple[str, float]]  # the 24 months ending at the financial year end, for charts


@lru_cache(maxsize=1)
def prices() -> dict[str, dict]:
    """series -> {"unit": str, "months": {"YYYY-MM": price}}."""
    out: dict[str, dict] = {}
    with DATA.open(newline="") as handle:
        for row in csv.DictReader(handle):
            item = out.setdefault(row["series"], {"unit": row["unit"], "months": {}})
            item["months"][row["month"]] = float(row["price"])
    return out


def source_note() -> str:
    return SOURCE.read_text().strip() if SOURCE.exists() else "World Bank Commodity Price Data (The Pink Sheet). Licence: CC BY 4.0."


def latest_month() -> str:
    return max(max(item["months"]) for item in prices().values())


def guess_sector(industry: str) -> str | None:
    text = industry.lower()
    for sector, (words, _) in SECTORS.items():
        if any(word in text for word in words):
            return sector
    return None


def year_end_month(run: Run) -> int | None:
    """The month the financial year ends, read from statement dates such as 'As at June 30, 2025'."""
    # The statement pages behind the verified figures, and the page before each (a statement's second page has no
    # title); the whole report only when those pages carry no date.
    sources = {r.source_page for r in run.reviews if r.source_page}
    near = sources | {n - 1 for n in sources}
    for texts in ([p.text for p in run.pages if p.number in near], [p.text for p in run.pages]):
        counts: dict[int, int] = {}
        for text in texts:
            for m in YEAR_END.finditer(" ".join(text.split())):
                if int(m.group(4)) == run.company.financial_year:
                    month = list(calendar.month_name).index(m.group(2).title())
                    counts[month] = counts.get(month, 0) + 1
        if counts:
            return max(counts, key=counts.get)
    return None


def window(end_year: int, end_month: int, length: int = 12) -> list[str]:
    """The `length` months ending at end_year-end_month, as YYYY-MM strings, oldest first."""
    months, year, month = [], end_year, end_month
    for _ in range(length):
        months.append(f"{year}-{month:02d}")
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return months[::-1]


def financial_year_prices(series: str, end_year: int, end_month: int) -> CommodityYear | None:
    """Average price over the financial year and the year before. None when the year is not fully covered."""
    item = prices().get(series)
    if item is None:
        return None
    current, prior = window(end_year, end_month), window(end_year - 1, end_month)
    if not all(m in item["months"] for m in current):
        return None
    average = sum(item["months"][m] for m in current) / 12
    prior_average = sum(item["months"][m] for m in prior) / 12 if all(m in item["months"] for m in prior) else None
    change = (average - prior_average) / prior_average if prior_average else None
    return CommodityYear(series, item["unit"], average, prior_average, change,
                         [(m, item["months"][m]) for m in prior + current if m in item["months"]])


def sector_context(sector: str, end_year: int, end_month: int) -> list[CommodityYear]:
    return [c for c in (financial_year_prices(s, end_year, end_month) for s in SECTORS[sector][1]) if c]
