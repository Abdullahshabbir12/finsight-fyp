"""Ordered field catalogues, shared by extraction, verification and reporting.

Non-financial companies use FIELDS; banks use BANK_FIELDS, because banks report interest, deposits and
advances instead of revenue, current assets and inventory. Keys shared by both mean the same thing.
"""
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
BANK_FIELDS = {
    "interest_earned": "Mark-up / Interest Earned",
    "interest_expensed": "Mark-up / Interest Expensed",
    "net_interest_income": "Net Mark-up / Interest Income",
    "non_interest_income": "Total Non-Mark-up / Non-Interest Income",
    "total_income": "Total Income",
    "operating_expenses": "Total Non-Mark-up / Interest Expenses",
    "profit_before_provisions": "Profit Before Credit Loss Allowance / Provisions",
    "provisions": "Credit Loss Allowance / Provisions (net charge)",
    "profit_before_tax": "Profit Before Tax",
    "tax_expense": "Tax Expense",
    "net_profit": "Net Profit / Profit After Tax",
    "eps": "EPS",
    "total_assets": "Total Assets",
    "cash_and_treasury": "Cash and Balances with Treasury Banks",
    "lendings": "Lendings to Financial Institutions",
    "investments": "Investments",
    "advances_net": "Advances / Islamic Financing (net)",
    "total_liabilities": "Total Liabilities",
    "deposits": "Deposits and Other Accounts",
    "borrowings": "Borrowings",
    "equity": "Shareholders' Equity",
    "gross_advances": "Gross Advances / Financing",
    "non_performing_loans": "Non-Performing Advances / Financing",
    "npl_provisions": "Credit Loss Allowance Held Against Non-Performing Advances",
    "casa_deposits": "Current and Savings Deposits",
    "capital_adequacy_ratio": "Capital Adequacy Ratio (reported)",
    "number_of_shares": "Number of Shares",
    "net_interest_income_prior_year": "Net Mark-up / Interest Income (prior year)",
    "net_profit_prior_year": "Net Profit (prior year)",
    "total_assets_prior_year": "Total Assets (prior year)",
    "advances_net_prior_year": "Advances / Islamic Financing, net (prior year)",
    "deposits_prior_year": "Deposits and Other Accounts (prior year)",
    "equity_prior_year": "Shareholders' Equity (prior year)",
}
SECTORS = {"general": FIELDS, "bank": BANK_FIELDS}
# Every known field, for labels and validation; a run uses only its sector's catalogue.
LABELS = {**FIELDS, **BANK_FIELDS}
PRIOR_SUFFIX = "_prior_year"
PRIOR_FIELDS = [k for k in FIELDS if k.endswith(PRIOR_SUFFIX)]


def catalog(sector: str) -> dict[str, str]:
    return SECTORS[sector]


def base_field(field: str) -> str:
    """The current-year field a prior-year field compares with, e.g. revenue_prior_year -> revenue."""
    return field.removesuffix(PRIOR_SUFFIX)


def expected_year(field: str, financial_year: int) -> int:
    return financial_year - 1 if field.endswith(PRIOR_SUFFIX) else financial_year


def internal_unit(field: str) -> str:
    field = base_field(field)
    if field == "capital_adequacy_ratio":
        return "%"
    return "shares" if field == "number_of_shares" else "PKR/share" if field == "eps" else "PKR"
