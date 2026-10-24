import pytest

from analytics import (
    CPI_U, bootstrap_ci, linear_regression, median, pearson,
    permutation_pvalue, rank, share_by_column, spearman, to_real_dollars,
)


def test_to_real_dollars_identity_in_base_year():
    assert to_real_dollars(100, 2025) == pytest.approx(100)


def test_to_real_dollars_scales_by_cpi_ratio():
    assert to_real_dollars(1, 1980) == pytest.approx(CPI_U[2025] / CPI_U[1980])


def test_to_real_dollars_clamps_and_rejects_bad_years():
    assert to_real_dollars(100, 2030) == pytest.approx(100)
    assert to_real_dollars(100, "") is None


def test_median_even_and_odd():
    assert median([3, 1, 2]) == 2
    assert median([4, 1, 3, 2]) == 2.5


def test_rank_handles_ties():
    assert rank([10, 20, 20, 30]) == [1, 2.5, 2.5, 4]


def test_spearman_is_one_for_monotonic_nonlinear():
    x = [1, 2, 3, 4, 5]
    y = [v ** 3 for v in x]
    assert spearman(x, y) == pytest.approx(1.0)
    assert pearson(x, y) < 1.0


def test_constant_variable_gives_zero_correlation():
    assert pearson([1, 2, 3], [5, 5, 5]) == 0.0


def test_linear_regression_exact_fit():
    slope, intercept, r2 = linear_regression([0, 1, 2], [1, 3, 5])
    assert (slope, intercept, r2) == pytest.approx((2, 1, 1))


def test_permutation_pvalue_small_for_strong_association():
    x = list(range(30))
    assert permutation_pvalue(x, x, n_perm=500) < 0.01


def test_permutation_pvalue_large_for_no_association():
    x = list(range(30))
    y = [5, 1, 9, 3, 7] * 6
    assert permutation_pvalue(x, y, n_perm=500) > 0.05


def test_bootstrap_ci_contains_median_and_is_reproducible():
    vals = [10, 50, 80, 120, 200, 260, 400, 900]
    lo, hi = bootstrap_ci(vals)
    assert lo <= median(vals) <= hi
    assert bootstrap_ci(vals) == (lo, hi)


def test_share_by_column_handles_missing_and_zero_totals():
    shares = share_by_column({"Drama": {"1970s": 50}}, {"1970s": 200, "1980s": 0})
    assert shares == {"Drama": {"1970s": 25.0, "1980s": 0.0}}
