"""Bundled synthetic example; never represents a listed company."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from src.catalog import FIELDS
from src.models import Company, FinancialField, Page, Run

DEMO_VALUES = [1000, 650, 350, 180, 30, 150, 45, 105, 1500, 600, 180, 150,
               120, 650, 300, 400, 850, 130, 80, 10.5, 10]


def demo_run() -> Run:
    company = Company(name="Cedar Manufacturing (Synthetic)", ticker="DEMO",
                      industry="Manufacturing", financial_year=2025)
    fields = []
    texts = {1: "SYNTHETIC Income Statement - Consolidated - 2025\nPKR million except EPS\n",
             2: "SYNTHETIC Statement of Financial Position - Consolidated - 2025\nPKR million\n",
             3: "SYNTHETIC Cash Flow and Other Data - Consolidated - 2025\nPKR million; shares in millions\n"}
    for i, (key, value) in enumerate(zip(FIELDS, DEMO_VALUES)):
        page = 1 if i < 8 else 2 if i < 17 else 3
        unit = "PKR/share" if key == "eps" else "shares million" if key == "number_of_shares" else "PKR million"
        source = f"{FIELDS[key]} | 2025 | {value} | {unit}"
        texts[page] += source + "\n"
        fields.append(FinancialField(field_name=key, reporting_year=2025, raw_value=str(value),
                      normalized_value=Decimal(str(value)) * (1 if key == "eps" else 1000000),
                      unit=unit, source_page=page, source_text=source, confidence=0.98, status="extracted"))
    return Run(id=str(uuid4()), company=company, is_demo=True,
               filename="Synthetic teaching example (no original PDF)",
               pages=[Page(number=p, text=t) for p, t in texts.items()], fields=fields,
               created_at=datetime.now(timezone.utc).isoformat(), timings={"pdf_seconds": 0, "extraction_seconds": 0})
