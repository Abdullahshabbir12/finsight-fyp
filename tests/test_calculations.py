from decimal import Decimal
import pytest
from src.calculations.ratios import SPECS, calculate, calculate_ratio
from src.demo import demo_run
from src.validation.review import commit_review, review_rows

EXPECTED = {"gross_profit_margin": "0.35", "operating_margin": "0.18", "net_profit_margin": "0.105",
            "return_on_assets": "0.07", "return_on_equity": str(Decimal(105) / Decimal(850)),
            "current_ratio": "2", "quick_ratio": "1.4", "debt_to_equity": str(Decimal(400) / Decimal(850)),
            "debt_ratio": str(Decimal(650) / Decimal(1500)), "interest_coverage": "6",
            "operating_cash_flow_margin": "0.13", "operating_cash_flow_to_debt": "0.325",
            "asset_turnover": str(Decimal(1000) / Decimal(1500)), "receivables_turnover": str(Decimal(1000) / Decimal(150))}


@pytest.fixture
def values():
    return {f.field_name: f.normalized_value for f in demo_run().fields}


@pytest.mark.parametrize("name", SPECS)
def test_all_normal_ratios(name, values):
    assert calculate_ratio(name, values).value == Decimal(EXPECTED[name])


@pytest.mark.parametrize("name", SPECS)
@pytest.mark.parametrize("bad", [Decimal(0), Decimal(-1), None])
def test_all_denominators(name, bad, values):
    values[SPECS[name].denominator] = bad
    metric = calculate_ratio(name, values)
    assert metric.value is None and metric.reason


@pytest.mark.parametrize("name", SPECS)
def test_each_missing_input(name, values):
    spec = SPECS[name]
    for key in (*spec.numerator, spec.denominator):
        reduced = {k: v for k, v in values.items() if k != key}
        assert calculate_ratio(name, reduced).value is None


@pytest.mark.parametrize("name", SPECS)
def test_all_negative_numerators(name, values):
    spec = SPECS[name]
    values[spec.numerator[0]] = Decimal(-100)
    result = calculate_ratio(name, values)
    if spec.allow_negative_numerator:
        assert result.value is not None and result.value < 0
    else:
        assert result.value is None


def test_quick_ratio_inventory_and_nonfinite(values):
    values["inventory"] = values["current_assets"] + 1
    assert calculate_ratio("quick_ratio", values).value is None
    values["net_profit"] = Decimal("NaN")
    assert calculate_ratio("net_profit_margin", values).value is None


def test_engine_requires_verified_values():
    run = demo_run()
    with pytest.raises(ValueError, match="verification"):
        calculate(run)
    rows = review_rows(run)
    for row in rows:
        row["Decision"] = "accept"
    commit_review(run, rows)
    assert len(calculate(run)) == 20  # 14 single-year + 3 growth + 3 average-balance


def test_growth_and_average_balance_ratios(values):
    from src.calculations.ratios import calculate_average, calculate_growth
    assert calculate_growth("revenue_growth", values).value == (Decimal(1000) - 900) / 900
    assert calculate_growth("operating_cash_flow_growth", values).value < 0
    assert calculate_average("return_on_average_assets", values).value == Decimal(105) / ((Decimal(1500) + 1400) / 2)
    assert calculate_average("average_receivables_turnover", values).value == Decimal(1000) / ((Decimal(150) + 140) / 2)


@pytest.mark.parametrize("prior", [Decimal(0), Decimal(-5), None])
def test_growth_needs_a_positive_prior_year(values, prior):
    from src.calculations.ratios import calculate_growth
    values["net_profit_prior_year"] = prior
    metric = calculate_growth("net_profit_growth", values)
    assert metric.value is None and metric.reason


def test_average_balance_must_be_positive(values):
    from src.calculations.ratios import calculate_average
    values["equity"], values["equity_prior_year"] = Decimal(-100), Decimal(50)
    assert calculate_average("return_on_average_equity", values).value is None
