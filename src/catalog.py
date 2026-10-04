"""One ordered field catalogue, shared by extraction, verification and reporting."""
FIELDS = {
    "revenue": "Revenue / Sales",
    "cost_of_sales": "Cost of Sales / COGS",
    "gross_profit": "Gross Profit",
    "operating_profit": "Operating Profit / EBIT",
    "finance_cost": "Finance Cost / Interest Expense",
    "profit_before_tax": "Profit Before Tax",
    "tax_expense": "Tax Expense",
    "net_profit": "Net Profit / Profit After Tax",
    "total_assets": "Total Assets",
    "current_assets": "Current Assets",
    "inventory": "Inventory",
    "trade_receivables": "Trade Receivables",
    "cash_equivalents": "Cash and Cash Equivalents",
    "total_liabilities": "Total Liabilities",
    "current_liabilities": "Current Liabilities",
    "total_debt": "Total Debt / Borrowings",
    "equity": "Shareholders' Equity",
    "operating_cash_flow": "Operating Cash Flow",
    "capital_expenditure": "Capital Expenditure",
    "eps": "EPS",
    "number_of_shares": "Number of Shares",
}


def internal_unit(field: str) -> str:
    return "shares" if field == "number_of_shares" else "PKR/share" if field == "eps" else "PKR"
