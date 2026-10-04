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
    # Prior-year comparatives for growth rates and average balances (key fields only, to limit review work).
    "revenue_prior_year": "Revenue / Sales (prior year)",
    "net_profit_prior_year": "Net Profit (prior year)",
    "operating_cash_flow_prior_year": "Operating Cash Flow (prior year)",
    "total_assets_prior_year": "Total Assets (prior year)",
    "equity_prior_year": "Shareholders' Equity (prior year)",
    "trade_receivables_prior_year": "Trade Receivables (prior year)",
}
PRIOR_SUFFIX = "_prior_year"
PRIOR_FIELDS = [k for k in FIELDS if k.endswith(PRIOR_SUFFIX)]


def base_field(field: str) -> str:
    """The current-year field a prior-year field compares with, e.g. revenue_prior_year -> revenue."""
    return field.removesuffix(PRIOR_SUFFIX)


def expected_year(field: str, financial_year: int) -> int:
    return financial_year - 1 if field.endswith(PRIOR_SUFFIX) else financial_year


def internal_unit(field: str) -> str:
    field = base_field(field)
    return "shares" if field == "number_of_shares" else "PKR/share" if field == "eps" else "PKR"
