"""Pure-Python statistics used by the dashboard.

Kept free of network calls and third-party dependencies so every function can be
unit-tested in isolation (see tests/test_analytics.py).
"""
import math
import random

# ── Inflation ──────────────────────────────────────────────────────────────
# US CPI-U, all items, annual average (1982-84 = 100). Source: U.S. Bureau of
# Labor Statistics. 1913–2020 from the BLS historical CPI-U table; 2021–2025
# from BLS annual averages. Update CPI_BASE_YEAR when a new full year is published.
CPI_U = {
    1913: 9.9, 1914: 10.0, 1915: 10.1, 1916: 10.9, 1917: 12.8, 1918: 15.1,
    1919: 17.3, 1920: 20.0, 1921: 17.9, 1922: 16.8, 1923: 17.1, 1924: 17.1,
    1925: 17.5, 1926: 17.7, 1927: 17.4, 1928: 17.1, 1929: 17.1, 1930: 16.7,
    1931: 15.2, 1932: 13.7, 1933: 13.0, 1934: 13.4, 1935: 13.7, 1936: 13.9,
    1937: 14.4, 1938: 14.1, 1939: 13.9, 1940: 14.0, 1941: 14.7, 1942: 16.3,
    1943: 17.3, 1944: 17.6, 1945: 18.0, 1946: 19.5, 1947: 22.3, 1948: 24.1,
    1949: 23.8, 1950: 24.1, 1951: 26.0, 1952: 26.5, 1953: 26.7, 1954: 26.9,
    1955: 26.8, 1956: 27.2, 1957: 28.1, 1958: 28.9, 1959: 29.1, 1960: 29.6,
    1961: 29.9, 1962: 30.2, 1963: 30.6, 1964: 31.0, 1965: 31.5, 1966: 32.4,
    1967: 33.4, 1968: 34.8, 1969: 36.7, 1970: 38.8, 1971: 40.5, 1972: 41.8,
    1973: 44.4, 1974: 49.3, 1975: 53.8, 1976: 56.9, 1977: 60.6, 1978: 65.2,
    1979: 72.6, 1980: 82.4, 1981: 90.9, 1982: 96.5, 1983: 99.6, 1984: 103.9,
    1985: 107.6, 1986: 109.6, 1987: 113.6, 1988: 118.3, 1989: 124.0,
    1990: 130.7, 1991: 136.2, 1992: 140.3, 1993: 144.5, 1994: 148.2,
    1995: 152.4, 1996: 156.9, 1997: 160.5, 1998: 163.0, 1999: 166.6,
    2000: 172.2, 2001: 177.1, 2002: 179.9, 2003: 184.0, 2004: 188.9,
    2005: 195.3, 2006: 201.6, 2007: 207.342, 2008: 215.303, 2009: 214.537,
    2010: 218.056, 2011: 224.939, 2012: 229.594, 2013: 232.957,
    2014: 236.736, 2015: 237.017, 2016: 240.007, 2017: 245.120,
    2018: 251.107, 2019: 255.657, 2020: 258.811, 2021: 270.970,
    2022: 292.655, 2023: 304.702, 2024: 313.689, 2025: 321.943,
}
CPI_BASE_YEAR = 2025


def to_real_dollars(amount, year, base_year=CPI_BASE_YEAR):
    """Convert a nominal amount from `year` into `base_year` dollars using CPI-U.

    Years outside the table are clamped to the nearest available year
    (e.g. a 2026 release is treated as 2025 dollars). Returns None when the
    year cannot be parsed.
    """
    try:
        year = int(year)
    except (TypeError, ValueError):
        return None
    lo, hi = min(CPI_U), max(CPI_U)
    year = max(lo, min(hi, year))
    return amount * CPI_U[base_year] / CPI_U[year]


# ── Descriptive statistics ────────────────────────────────────────────────
def mean(values):
    return sum(values) / len(values)


def median(values):
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def pearson(x, y):
    """Pearson correlation coefficient. Returns 0.0 when either variable is constant."""
    if len(x) < 2:
        return 0.0
    mx, my = mean(x), mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def rank(values):
    """Average ranks (1-based), ties share the mean of their positions."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x, y):
    """Spearman rank correlation (Pearson on average ranks, so ties are handled)."""
    return pearson(rank(x), rank(y))


def permutation_pvalue(x, y, stat=spearman, n_perm=2000, seed=42):
    """Two-sided permutation p-value for H0: no association between x and y.

    Shuffles y `n_perm` times and counts how often |stat| is at least as large
    as the observed one. Uses the (count + 1) / (n_perm + 1) correction so the
    p-value is never exactly 0.
    """
    rng = random.Random(seed)
    observed = abs(stat(x, y))
    y_perm = list(y)
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(y_perm)
        if abs(stat(x, y_perm)) >= observed:
            hits += 1
    return (hits + 1) / (n_perm + 1)


def linear_regression(x, y):
    """Ordinary least squares y = intercept + slope·x. Returns (slope, intercept, r2)."""
    mx, my = mean(x), mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx if sxx else 0.0
    intercept = my - slope * mx
    ss_res = sum((b - (slope * a + intercept)) ** 2 for a, b in zip(x, y))
    ss_tot = sum((b - my) ** 2 for b in y)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return slope, intercept, r2


def bootstrap_ci(values, stat=median, n_boot=2000, alpha=0.05, seed=42):
    """Percentile bootstrap confidence interval for `stat(values)`.

    Resamples `values` with replacement `n_boot` times and returns the
    (alpha/2, 1 - alpha/2) percentiles of the resampled statistic. Seeded so the
    dashboard shows the same interval for the same data on every refresh.
    """
    rng = random.Random(seed)
    n = len(values)
    boots = sorted(stat([values[rng.randrange(n)] for _ in range(n)])
                   for _ in range(n_boot))
    lo_idx = int(math.floor(alpha / 2 * n_boot))
    hi_idx = int(math.ceil((1 - alpha / 2) * n_boot)) - 1
    return boots[lo_idx], boots[hi_idx]


def share_by_column(counts, totals):
    """Turn {row: {col: count}} into {row: {col: % of totals[col]}}.

    Missing cells count as 0; columns whose total is 0 return 0 instead of
    dividing by zero.
    """
    return {
        row: {col: (100 * cells.get(col, 0) / totals[col]) if totals.get(col) else 0.0
              for col in totals}
        for row, cells in counts.items()
    }
