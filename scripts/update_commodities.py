"""Refresh BrokerLens's commodity price snapshot from the World Bank's monthly Pink Sheet workbook.

Usage: python scripts/update_commodities.py CMO-Historical-Data-Monthly.xlsx
Download the workbook from https://www.worldbank.org/en/research/commodity-markets ("Monthly prices", XLS).
World Bank datasets are licensed CC BY 4.0; the app credits the source wherever the prices are shown.
"""
import csv
import re
import sys
from pathlib import Path
from openpyxl import load_workbook

KEEP = ["Crude oil, Brent", "Coal, Australian", "Coal, South African", "Liquefied natural gas, Japan", "Cotton, A Index",
        "Urea", "DAP", "Iron ore, cfr spot", "Sugar, world", "Palm oil", "Soybean oil", "Wheat, US HRW", "Copper", "Aluminum"]
FIRST_YEAR = 2010
OUT = Path(__file__).resolve().parent.parent / "src" / "market" / "commodity_prices.csv"


def main(path: str) -> None:
    book = load_workbook(path, read_only=True, data_only=True)
    rows = list(book["Monthly Prices"].iter_rows(values_only=True))
    updated = next(str(r[0]) for r in rows[:6] if r[0] and str(r[0]).startswith("Updated on"))
    names = [re.sub(r"\s*\*+\s*$", "", str(n)).strip() if n else "" for n in rows[4]]
    units = [str(u).strip("()") if u else "" for u in rows[5]]
    columns = {name: i for i, name in enumerate(names) if name in KEEP}
    missing = set(KEEP) - set(columns)
    if missing:
        raise SystemExit(f"Series not found in the workbook: {sorted(missing)}")
    with OUT.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["month", "series", "unit", "price"])
        for row in rows[6:]:
            month = str(row[0] or "")
            if not re.fullmatch(r"\d{4}M\d{2}", month) or int(month[:4]) < FIRST_YEAR:
                continue
            for name, i in columns.items():
                if isinstance(row[i], (int, float)):
                    writer.writerow([f"{month[:4]}-{month[5:]}", name, units[i], row[i]])
    OUT.with_suffix(".txt").write_text(f"World Bank Commodity Price Data (The Pink Sheet), {updated}. Licence: CC BY 4.0.\n")
    print(f"Wrote {OUT} ({updated})")


if __name__ == "__main__":
    main(sys.argv[1])
