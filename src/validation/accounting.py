"""Findings only. Checks never change a financial value.

Each check returns a Finding: what was found, the verified figures behind it, the arithmetic, why it matters and what an
analyst could look at next. Thresholds are teaching heuristics, not industry benchmarks, and a finding is a prompt for
review, never evidence of misconduct.
"""
from decimal import Decimal
from src.catalog import LABELS, expected_year
from src.models import Finding, Run
from src.validation.review import verified_values

NONNEGATIVE = {"revenue", "cost_of_sales", "finance_cost", "total_assets", "current_assets", "inventory",
               "trade_receivables", "cash_equivalents", "total_liabilities", "current_liabilities", "total_debt", "number_of_shares",
               "revenue_prior_year", "total_assets_prior_year", "trade_receivables_prior_year"}
BANK_NONNEGATIVE = {"interest_earned", "interest_expensed", "total_assets", "cash_and_treasury", "lendings", "investments",
                    "advances_net", "deposits", "borrowings", "total_liabilities", "gross_advances", "non_performing_loans",
                    "npl_provisions", "casa_deposits", "operating_expenses", "number_of_shares", "capital_adequacy_ratio",
                    "deposits_prior_year", "advances_net_prior_year", "total_assets_prior_year"}
DIVERGENCE_POINTS = Decimal("0.25")  # profit growth exceeding cash-flow growth by 25 percentage points
RECEIVABLES_POINTS = Decimal("0.10")  # receivables growth exceeding revenue growth by 10 percentage points
HIGH_ACCRUALS = Decimal("0.10")  # accruals above 10% of average total assets
# Teaching references, not regulatory advice: SBP's minimum CAR is 10% plus a 1.5% capital conservation buffer.
SBP_MINIMUM_CAR = Decimal("11.5")
HIGH_INFECTION = Decimal("0.10")
# Profit / shares only approximates EPS (non-controlling interest, weighted shares, preference dividends), so the
# check is loose: it catches a share count off by a factor such as 10 or 1,000, not small differences.
EPS_BAND = (Decimal("0.5"), Decimal(2))
PRIORITY = {"high": 0, "medium": 1, "low": 2}

CHECK_FIGURES = "Open each figure on its PDF page and confirm the number, year column and statement basis."
SAME_COLUMN = "Confirm all the figures come from the same year column and the same (consolidated or standalone) statements."
SIGN = "This line is normally positive. A negative value usually means a deduction was entered with the wrong sign or another line was read."


def reconcile(left: Decimal, right: Decimal) -> tuple[bool, Decimal]:
    """Tolerance: greater of PKR 1 or 1% of the larger absolute side."""
    difference = left - right
    tolerance = max(Decimal(1), max(abs(left), abs(right)) * Decimal("0.01"))
    return abs(difference) <= tolerance, difference


def pkr(value: Decimal) -> str:
    """Accounting style: negatives in brackets, e.g. PKR (3.95) bn."""
    for scale, word in ((Decimal(10) ** 9, " bn"), (Decimal(10) ** 6, " m"), (Decimal(1), "")):
        if abs(value) >= scale or scale == 1:
            amount = f"{abs(value) / scale:,.2f}" if scale > 1 else f"{abs(value):,.0f}"
            return f"PKR ({amount}){word}" if value < 0 else f"PKR {amount}{word}"


def growth(values: dict, key: str) -> Decimal | None:
    prior = values.get(key + "_prior_year")
    return None if key not in values or not prior or prior <= 0 else (values[key] - prior) / prior


def extraction_notes(run: Run) -> list[str]:
    """Issues the checks raised on the AI's proposals, kept for the record after verification."""
    notes = []
    for field in run.fields:
        notes.extend(f"{LABELS[field.field_name]} extraction: {issue}" for issue in field.issues)
        if field.normalized_value is not None and field.reporting_year != expected_year(field.field_name, run.company.financial_year):
            notes.append(f"{LABELS[field.field_name]}: extracted reporting-period mismatch.")
    return notes


def validate_run(run: Run) -> list[str]:
    """Plain-text form: extraction notes, then every finding's detail."""
    return extraction_notes(run) + [f.detail for f in findings(run)]


def findings(run: Run) -> list[Finding]:
    values = verified_values(run)
    bank = run.company.sector == "bank"
    return shared_findings(values, bank) + (bank_findings(values) if bank else company_findings(values))


def by_priority(items: list[Finding]) -> list[Finding]:
    return sorted(items, key=lambda f: PRIORITY[f.priority])


def shared_findings(values: dict, bank: bool) -> list[Finding]:
    out = []
    key_fields = (("net_interest_income", "net_profit", "total_assets", "total_liabilities", "equity", "deposits", "advances_net")
                  if bank else ("revenue", "net_profit", "total_assets", "total_liabilities", "equity", "operating_cash_flow"))
    missing = [k for k in key_fields if k not in values]
    if missing:
        out.append(Finding(
            key="missing_key_values", category="Data completeness", priority="low", title="Key figures are unavailable",
            detail="Missing key verified values: " + ", ".join(LABELS[k] for k in missing) + ".",
            why="Ratios and checks that need these figures show N/A, so the analysis is less complete.",
            next_steps=["Look for the figure in the notes or on another statement page and enter it in Verify with evidence.",
                        "If the report genuinely does not print it, keep it unavailable; never estimate it."]))
    for key in sorted((BANK_NONNEGATIVE if bank else NONNEGATIVE) & values.keys()):
        if values[key] < 0:
            out.append(Finding(
                key="negative_" + key, category="Data check", priority="medium", title=f"{LABELS[key]} is negative",
                detail=f"{LABELS[key]} is negative. Confirm sign conventions and source; no automatic change was made.",
                fields=[key], calculation=f"{LABELS[key]} = {pkr(values[key])}", why=SIGN,
                next_steps=[CHECK_FIGURES, "Correct the sign in Verify if the brackets mark a deduction."]))
    if values.get("equity", Decimal(1)) <= 0:
        out.append(Finding(
            key="nonpositive_equity", category="Solvency", priority="high", title="Equity is zero or negative",
            detail="Equity is nonpositive; ROE and leverage ratios are N/A.", fields=["equity"],
            calculation=f"{LABELS['equity']} = {pkr(values['equity'])}",
            why="Accumulated losses have used up shareholders' capital, so liabilities exceed assets.",
            next_steps=["Read the auditor's report for a going-concern paragraph or emphasis of matter.",
                        "Check the directors' report for recapitalisation plans or sponsor support.",
                        "Check debt maturities and any covenant breaches in the borrowings note."]))
    if all(k in values for k in ("total_assets", "total_liabilities", "equity")):
        ok, difference = reconcile(values["total_assets"], values["total_liabilities"] + values["equity"])
        if not ok:
            out.append(Finding(
                key="balance_sheet_identity", category="Data check", priority="high",
                title="Assets do not equal liabilities plus equity",
                detail=f"Assets versus liabilities plus equity: difference PKR {difference:,.2f} exceeds the 1% (minimum PKR 1) "
                       "tolerance. Requires human review.",
                fields=["total_assets", "total_liabilities", "equity"],
                calculation=f"{pkr(values['total_assets'])} - ({pkr(values['total_liabilities'])} + {pkr(values['equity'])}) "
                            f"= {pkr(difference)}",
                why="A balance sheet always balances, so a gap means one figure was misread, comes from another column or "
                    "basis, or equity leaves out non-controlling interest.",
                next_steps=["Check whether total liabilities is a printed total or an unlabelled subtotal.",
                            "Check that equity includes non-controlling interest (for banks, the NET ASSETS figure).", SAME_COLUMN]))
    if values.get("number_of_shares", 0) > 0 and values.get("eps") and "net_profit" in values:
        implied = values["net_profit"] / values["number_of_shares"]
        if not EPS_BAND[0] <= implied / values["eps"] <= EPS_BAND[1]:
            out.append(Finding(
                key="share_count_vs_eps", category="Data check", priority="high", title="Share count does not fit reported EPS",
                detail=f"Net profit divided by the share count gives PKR {implied:,.2f} per share against reported EPS of PKR "
                       f"{values['eps']:,.2f}. Check the share count (issued shares, not authorised capital or rupee share "
                       "capital) and its unit.",
                fields=["net_profit", "number_of_shares", "eps"],
                calculation=f"{pkr(values['net_profit'])} / {values['number_of_shares']:,.0f} shares = PKR {implied:,.2f} per share; "
                            f"reported EPS PKR {values['eps']:,.2f}",
                why="EPS is profit per share, so profit divided by the share count should be close to it. Being off by more "
                    "than half or double usually means the share count is wrong.",
                next_steps=["Use issued, subscribed and paid-up shares, not authorised capital.",
                            "Make sure the count is in shares, not rupees of share capital or thousands of shares."]))
    return out


def identity(values: dict, key: str, title: str, label: str, total: str, parts: list[tuple[int, str]], note: str = "",
             priority: str = "high") -> list[Finding]:
    """A printed total that differs from the sum of its signed parts by more than the tolerance."""
    if not all(k in values for k in [total, *(k for _, k in parts)]):
        return []
    expected = sum((sign * values[k] for sign, k in parts), Decimal(0))
    ok, difference = reconcile(values[total], expected)
    if ok:
        return []
    terms = " ".join(f"{'+' if sign > 0 else '-'} {pkr(values[k])}" for sign, k in parts).lstrip("+ ")
    return [Finding(
        key=key, category="Data check", priority=priority, title=title,
        detail=f"{label}: difference PKR {difference:,.2f} exceeds the 1% (minimum PKR 1) tolerance. {note}Requires human review.",
        fields=[total, *(k for _, k in parts)],
        calculation=f"Printed {pkr(values[total])}; {terms} = {pkr(expected)}; difference {pkr(difference)}",
        why="Each line of the profit and loss account should add up to the next. A gap usually means a figure was misread "
            "or a line between them (such as share of associates or a levy) was left out.",
        next_steps=[CHECK_FIGURES, "Look for lines printed between these totals that explain the gap."])]


def exceeds(values: dict, smaller: str, larger: str, advice: str) -> list[Finding]:
    if smaller in values and larger in values and values[smaller] > values[larger]:
        return [Finding(
            key=f"{smaller}_exceeds_{larger}", category="Data check", priority="medium",
            title=f"{LABELS[smaller]} exceeds {LABELS[larger]}",
            detail=f"{LABELS[smaller]} exceeds {LABELS[larger]}. {advice}", fields=[smaller, larger],
            calculation=f"{pkr(values[smaller])} > {pkr(values[larger])}",
            why="The first figure is part of the second, so it cannot be larger. One of them is probably misread or in another unit.",
            next_steps=[CHECK_FIGURES, SAME_COLUMN])]
    return []


def bank_findings(values: dict) -> list[Finding]:
    out = []
    out += identity(values, "identity_net_interest_income", "Net interest income does not equal interest earned less expensed",
                    "Net interest income versus interest earned less expensed", "net_interest_income",
                    [(1, "interest_earned"), (-1, "interest_expensed")])
    out += identity(values, "identity_total_income", "Total income does not equal net interest plus non-interest income",
                    "Total income versus net interest plus non-interest income", "total_income",
                    [(1, "net_interest_income"), (1, "non_interest_income")])
    out += identity(values, "identity_profit_before_provisions", "Profit before provisions does not equal total income less expenses",
                    "Profit before provisions versus total income less operating expenses", "profit_before_provisions",
                    [(1, "total_income"), (-1, "operating_expenses")], "Share of associates or other items may explain a small gap. ",
                    priority="medium")
    out += identity(values, "identity_profit_before_tax", "Profit before tax does not equal profit before provisions less provisions",
                    "Profit before tax versus profit before provisions less provisions", "profit_before_tax",
                    [(1, "profit_before_provisions"), (-1, "provisions")], "A levy or a provision sign may explain it. ")
    out += identity(values, "identity_net_profit", "Profit after tax does not equal profit before tax less tax",
                    "Profit after tax versus profit before tax less tax", "net_profit",
                    [(1, "profit_before_tax"), (-1, "tax_expense")])
    advice = "Check units, the note used and the statement basis."
    for smaller, larger in [("non_performing_loans", "gross_advances"), ("advances_net", "gross_advances"),
                            ("casa_deposits", "deposits"), ("deposits", "total_liabilities"), ("npl_provisions", "non_performing_loans")]:
        out += exceeds(values, smaller, larger, advice)
    if all(k in values for k in ("gross_advances", "advances_net", "npl_provisions")):
        ok, difference = reconcile(values["gross_advances"], values["advances_net"] + values["npl_provisions"])
        if not ok and difference < 0:
            out.append(Finding(
                key="gross_advances_too_low", category="Data check", priority="medium",
                title="Gross advances look too low",
                detail="Gross advances are below net advances plus the allowance against non-performing advances. Gross "
                       "advances may omit some financing lines or be a single column; check the advances note.",
                fields=["gross_advances", "advances_net", "npl_provisions"],
                calculation=f"{pkr(values['gross_advances'])} < {pkr(values['advances_net'])} + {pkr(values['npl_provisions'])}",
                why="Net advances are gross advances less allowances, so gross must be at least net plus the allowance on "
                    "non-performing advances.",
                next_steps=["Use the TOTAL column of the advances note (performing plus non-performing).",
                            "Include every financing line (e.g. Islamic financing and conventional advances)."]))
    car = values.get("capital_adequacy_ratio")
    if car is not None and not 0 < car < 100:
        out.append(Finding(
            key="car_unit", category="Data check", priority="high", title="Capital adequacy ratio is not a percentage",
            detail="Capital adequacy ratio is outside 0-100%. Enter it as a percentage, e.g. 18.25.",
            fields=["capital_adequacy_ratio"], calculation=f"Entered {car}",
            why="The ratio is printed as a percentage; a value outside 0-100 was probably entered in the wrong form.",
            next_steps=["Enter the bank's total capital adequacy ratio as printed, e.g. 18.25."]))
    elif car is not None and car < SBP_MINIMUM_CAR:
        out.append(Finding(
            key="low_capital_adequacy", category="Capital", priority="high", title="Capital adequacy is below the SBP reference",
            detail=f"Reported capital adequacy is below {SBP_MINIMUM_CAR}%, a teaching reference for SBP's minimum including the "
                   "conservation buffer. Potential capital warning indicator; check current SBP requirements and the bank's disclosures.",
            fields=["capital_adequacy_ratio"], calculation=f"Reported {car}% against a {SBP_MINIMUM_CAR}% reference",
            why="Capital adequacy is the loss-absorbing capital held against risk-weighted assets; SBP sets minimums.",
            next_steps=["Compare CET1 and Tier 1 ratios with SBP minimums in the capital adequacy note.",
                        "Look for capital-raising plans, regulatory relaxations or dividend restrictions."]))
    if values.get("gross_advances") and "non_performing_loans" in values:
        ratio = values["non_performing_loans"] / values["gross_advances"]
        if ratio > HIGH_INFECTION:
            out.append(Finding(
                key="high_infection", category="Asset quality", priority="high",
                title="Non-performing advances are above 10% of gross advances",
                detail="Non-performing loans exceed 10% of gross advances. Potential asset-quality warning indicator (teaching "
                       "heuristic); review provisioning and the classification note.",
                fields=["non_performing_loans", "gross_advances"],
                calculation=f"{pkr(values['non_performing_loans'])} / {pkr(values['gross_advances'])} = {ratio:.1%}",
                why="A high share of loans not being repaid can reduce future income and require more provisions.",
                next_steps=["Check which sectors drive non-performing advances (concentration note).",
                            "Compare provision coverage and any general provision.",
                            "Compare with the prior year's report to see whether the ratio is rising."]))
    provisions, before_tax = values.get("provisions"), values.get("profit_before_tax")
    if provisions is not None and provisions < 0 and before_tax and before_tax > 0:
        share = -provisions / before_tax
        out.append(Finding(
            key="provision_reversal", category="Earnings quality", priority="medium",
            title="Profit includes a net provision reversal",
            detail=f"Provisions were a net reversal of {pkr(-provisions)}, adding {share:.1%} of profit before tax. Reversals "
                   "are unlikely to repeat every year, so core earnings are lower than reported profit. An indicator for "
                   "review, not a finding of wrongdoing.",
            fields=["provisions", "profit_before_tax", "profit_before_provisions"],
            calculation=f"Reversal {pkr(-provisions)} / profit before tax {pkr(before_tax)} = {share:.1%}",
            why="Earnings that depend on releasing past provisions are less likely to recur than income from lending and fees.",
            next_steps=["Read the credit loss allowance note: what drove the reversal (recoveries, settlements, model or IFRS 9 changes)?",
                        "Compare growth in profit before provisions with growth in profit before tax."]))
    return out


def company_findings(values: dict) -> list[Finding]:
    out = []
    if all(k in values for k in ("gross_profit", "revenue", "cost_of_sales")):
        expected = values["revenue"] - values["cost_of_sales"]
        ok, difference = reconcile(values["gross_profit"], expected)
        if not ok:
            out.append(Finding(
                key="gross_profit_identity", category="Data check", priority="high",
                title="Gross profit does not equal revenue less cost of sales",
                detail=f"Gross profit versus revenue less cost of sales: difference PKR {difference:,.2f} exceeds the 1% (minimum PKR 1) "
                       "tolerance. Requires human review.",
                fields=["gross_profit", "revenue", "cost_of_sales"],
                calculation=f"{pkr(values['revenue'])} - {pkr(values['cost_of_sales'])} = {pkr(expected)}; "
                            f"printed gross profit {pkr(values['gross_profit'])}",
                why="Gross profit is revenue less cost of sales, so a gap means a figure was misread or comes from another column.",
                next_steps=[CHECK_FIGURES, SAME_COLUMN]))
    accruals = None
    if all(k in values for k in ("net_profit", "operating_cash_flow", "total_assets", "total_assets_prior_year")):
        average = (values["total_assets"] + values["total_assets_prior_year"]) / 2
        if average > 0:
            accruals = (values["net_profit"] - values["operating_cash_flow"]) / average
    if all(k in values for k in ("net_profit", "operating_cash_flow")) and values["net_profit"] > values["operating_cash_flow"]:
        profit, cash = values["net_profit"], values["operating_cash_flow"]
        serious = cash < 0 or (accruals is not None and accruals > HIGH_ACCRUALS)
        out.append(Finding(
            key="profit_above_cash_flow", category="Earnings quality", priority="medium" if serious else "low",
            title="Profit is higher than operating cash flow",
            detail="Net profit exceeds operating cash flow. Cash conversion is an indicator requiring further review; this is not evidence of misconduct.",
            fields=["net_profit", "operating_cash_flow"],
            calculation=(f"Operating cash flow {pkr(cash)} / net profit {pkr(profit)} = {cash / profit:.2f}x" if profit > 0
                         else f"Net profit {pkr(profit)}; operating cash flow {pkr(cash)}"),
            why="Profit that does not arrive as cash may reflect rising receivables or inventory, non-cash gains or timing. "
                "When it persists, earnings are of lower quality.",
            next_steps=["In the cash flow statement, find which working-capital lines absorbed cash (receivables, inventory, payables).",
                        "Look for non-cash gains in profit, such as fair-value or disposal gains.",
                        "Compare with earlier years' reports: a one-year timing effect matters less than a pattern."]))
    if accruals is not None and accruals > HIGH_ACCRUALS:
        out.append(Finding(
            key="high_accruals", category="Earnings quality", priority="medium",
            title="A large part of profit is accruals, not cash",
            detail=f"Accruals ((net profit - operating cash flow) / average total assets) are {accruals:.1%}, above the 10% "
                   "teaching threshold. A large accrual share has been linked to less persistent earnings (Sloan, 1996); "
                   "it is a prompt for review, not evidence of misstatement.",
            fields=["net_profit", "operating_cash_flow", "total_assets", "total_assets_prior_year"],
            calculation=f"({pkr(values['net_profit'])} - {pkr(values['operating_cash_flow'])}) / "
                        f"(({pkr(values['total_assets'])} + {pkr(values['total_assets_prior_year'])}) / 2) = {accruals:.1%}",
            why="Accruals are the part of profit recorded before cash changes hands. Large accruals depend more on "
                "estimates and tend to reverse.",
            next_steps=["Break the gap down using the working-capital lines in the cash flow statement.",
                        "Check the revenue recognition and receivables notes for changes in policy or credit terms."]))
    profit_growth, cash_growth = growth(values, "net_profit"), growth(values, "operating_cash_flow")
    if profit_growth is not None and cash_growth is not None and profit_growth - cash_growth > DIVERGENCE_POINTS:
        out.append(Finding(
            key="profit_outgrowing_cash_flow", category="Earnings quality", priority="medium",
            title="Profit grew much faster than operating cash flow",
            detail="Net profit grew materially faster than operating cash flow year on year. Divergence between profit growth "
                   "and cash flow is an indicator requiring further review; it is not evidence of misconduct.",
            fields=["net_profit", "net_profit_prior_year", "operating_cash_flow", "operating_cash_flow_prior_year"],
            calculation=f"Net profit growth {profit_growth:.1%}; operating cash flow growth {cash_growth:.1%}",
            why="If profit rises while cash flow does not, more of the profit sits in receivables, inventory or other accruals.",
            next_steps=["Compare the change in trade receivables and inventory with the change in revenue.",
                        "Check for one-off gains included in profit this year."]))
    sales_growth, receivables_growth = growth(values, "revenue"), growth(values, "trade_receivables")
    if sales_growth is not None and receivables_growth is not None and receivables_growth - sales_growth > RECEIVABLES_POINTS:
        days = values["trade_receivables"] / values["revenue"] * 365 if values["revenue"] > 0 else None
        days_prior = values["trade_receivables_prior_year"] / values["revenue_prior_year"] * 365
        out.append(Finding(
            key="receivables_outpacing_revenue", category="Earnings quality", priority="medium",
            title="Receivables grew faster than revenue",
            detail=f"Trade receivables grew {receivables_growth:.1%} while revenue grew {sales_growth:.1%}"
                   + (f"; days of sales in receivables moved from {days_prior:,.0f} to {days:,.0f}" if days is not None else "")
                   + ". Receivables outpacing sales is an indicator requiring further review (teaching threshold: 10 "
                     "percentage points), not evidence of misconduct.",
            fields=["trade_receivables", "trade_receivables_prior_year", "revenue", "revenue_prior_year"],
            calculation=f"Receivables growth {receivables_growth:.1%} - revenue growth {sales_growth:.1%} = "
                        f"{receivables_growth - sales_growth:.1%}; days of sales = receivables / revenue x 365",
            why="Customers taking longer to pay can mean looser credit terms, collection problems or revenue recognised early.",
            next_steps=["Read the trade debts note: ageing, overdue balances and the expected credit loss allowance.",
                        "Check for related-party receivables.",
                        "Check the directors' report for changes in credit terms or customer mix."]))
    if all(k in values for k in ("current_assets", "current_liabilities")) and values["current_assets"] < values["current_liabilities"]:
        out.append(Finding(
            key="current_liabilities_exceed_current_assets", category="Liquidity", priority="medium",
            title="Current liabilities exceed current assets",
            detail="Current assets are below current liabilities. Potential liquidity warning indicator; consider the operating cycle and industry.",
            fields=["current_assets", "current_liabilities"],
            calculation=f"{pkr(values['current_assets'])} / {pkr(values['current_liabilities'])} = "
                        f"{values['current_assets'] / values['current_liabilities']:.2f}x" if values["current_liabilities"] > 0 else "",
            why="Short-term obligations are larger than short-term assets, so the company relies on operating cash, new "
                "borrowing or rolling over credit lines.",
            next_steps=["Check short-term borrowings and unused running-finance limits in the borrowings note.",
                        "Consider whether negative working capital is normal for this business, e.g. customer advances."]))
    if all(k in values for k in ("total_debt", "equity")) and values["total_debt"] > values["equity"]:
        out.append(Finding(
            key="debt_above_equity", category="Leverage", priority="medium", title="Debt is higher than equity",
            detail="Debt exceeds equity. Potential leverage warning indicator; the threshold is a simple teaching heuristic, not an industry benchmark.",
            fields=["total_debt", "equity"],
            calculation=f"{pkr(values['total_debt'])} / {pkr(values['equity'])} = {values['total_debt'] / values['equity']:.2f}x"
                        if values["equity"] > 0 else "",
            why="More debt than equity raises fixed interest costs and the risk that a weak year strains repayments.",
            next_steps=["Check interest coverage and the trend in finance cost.",
                        "Read the borrowings note for maturities, rates and covenants."]))
    advice = "Check units, classification, and statement basis."
    for smaller, larger in [("inventory", "current_assets"), ("current_assets", "total_assets"),
                            ("current_liabilities", "total_liabilities"), ("total_debt", "total_liabilities")]:
        out += exceeds(values, smaller, larger, advice)
    return out


STATUS_LABEL = {"open": "Open", "confirmed": "Confirmed concern", "investigating": "Under investigation", "dismissed": "Dismissed"}


def decide(run: Run, finding: Finding, status: str, comment: str, at: str) -> None:
    """Record an analyst's decision on a finding, keeping every earlier decision as history."""
    from src.models import FindingDecision
    comment = comment.strip()
    if status == "dismissed" and not comment:
        raise ValueError("Explain why the finding is dismissed, e.g. 'gap is share of associates, printed on page 439'.")
    run.finding_decisions.setdefault(finding.key, []).append(
        FindingDecision(status=status, comment=comment, detail=finding.detail, at=at))


def current_decision(run: Run, finding: Finding):
    """The latest decision, and whether the finding's wording has changed since (e.g. after a corrected value)."""
    history = run.finding_decisions.get(finding.key)
    if not history:
        return None, False
    return history[-1], history[-1].detail != finding.detail
