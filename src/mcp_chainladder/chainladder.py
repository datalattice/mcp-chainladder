"""Chain ladder reserving calculations.

Pure-numeric core, no GUI. Operates on cumulative loss triangles.

Conventions:
    triangle[i][j] = cumulative losses for accident year i at development age j+1.
    Unobserved (lower-right) cells are represented as None or NaN.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence


Number = Optional[float]


def _is_obs(x: Number) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


@dataclass
class ChainLadderResult:
    triangle: List[List[Number]]
    volume_factors: List[float]          # all-year volume-weighted age-to-age
    simple_factors: List[float]          # simple average of individual link ratios
    selected_factors: List[float]        # what we actually use to project
    individual_factors: List[List[Number]]  # per-row link ratios C[i,j+1]/C[i,j]
    cdf: List[float]                     # cumulative dev factors to ultimate per dev age
    latest_diagonal: List[float]         # most recent observed value per accident row
    ultimates: List[float]
    ibnr: List[float]

    @property
    def n_acc(self) -> int:
        return len(self.triangle)

    @property
    def n_dev(self) -> int:
        return len(self.triangle[0]) if self.triangle else 0

    @property
    def total_latest(self) -> float:
        return float(sum(self.latest_diagonal))

    @property
    def total_ultimate(self) -> float:
        return float(sum(self.ultimates))

    @property
    def total_ibnr(self) -> float:
        return float(sum(self.ibnr))


def volume_weighted_factors(
    triangle: Sequence[Sequence[Number]],
    excluded: Optional[set] = None,
) -> List[float]:
    """All-year volume-weighted age-to-age factors.

    f_j = sum_i C[i, j+1] / sum_i C[i, j],
    summed over rows where both cells are observed and (i, j) is not excluded.

    ``excluded`` is a set of (row_i, dev_j) tuples — each identifies a single
    link ratio (between C[i, j] and C[i, j+1]) that should be dropped from
    both the volume and simple averages. Useful for outlier handling.
    """
    if not triangle:
        return []
    excluded = excluded or set()
    n_dev = len(triangle[0])
    factors: List[float] = []
    for j in range(n_dev - 1):
        num = 0.0
        den = 0.0
        for i, row in enumerate(triangle):
            if (i, j) in excluded:
                continue
            a, b = row[j], row[j + 1]
            if _is_obs(a) and _is_obs(b):
                num += float(b)
                den += float(a)
        factors.append(num / den if den > 0 else 1.0)
    return factors


def simple_average_factors(
    triangle: Sequence[Sequence[Number]],
    excluded: Optional[set] = None,
) -> List[float]:
    """Unweighted average of individual link ratios per development period."""
    if not triangle:
        return []
    excluded = excluded or set()
    n_dev = len(triangle[0])
    factors: List[float] = []
    for j in range(n_dev - 1):
        ratios = []
        for i, row in enumerate(triangle):
            if (i, j) in excluded:
                continue
            a, b = row[j], row[j + 1]
            if _is_obs(a) and _is_obs(b) and float(a) > 0:
                ratios.append(float(b) / float(a))
        factors.append(sum(ratios) / len(ratios) if ratios else 1.0)
    return factors


def individual_link_ratios(triangle: Sequence[Sequence[Number]]) -> List[List[Number]]:
    """Per-row age-to-age link ratios."""
    out: List[List[Number]] = []
    n_dev = len(triangle[0]) if triangle else 0
    for row in triangle:
        row_out: List[Number] = []
        for j in range(n_dev - 1):
            a, b = row[j], row[j + 1]
            if _is_obs(a) and _is_obs(b) and float(a) > 0:
                row_out.append(float(b) / float(a))
            else:
                row_out.append(None)
        out.append(row_out)
    return out


def cumulative_dev_factors(selected: Sequence[float], tail: float = 1.0) -> List[float]:
    """CDF[j] = product(selected[j:]) * tail. Length = len(selected) + 1."""
    n = len(selected)
    cdf = [1.0] * (n + 1)
    cdf[n] = float(tail)
    for j in range(n - 1, -1, -1):
        cdf[j] = cdf[j + 1] * float(selected[j])
    return cdf


def latest_diagonal_values(triangle: Sequence[Sequence[Number]]) -> List[float]:
    """For each row, the right-most observed cumulative value."""
    out: List[float] = []
    for row in triangle:
        last = 0.0
        for v in row:
            if _is_obs(v):
                last = float(v)
        out.append(last)
    return out


def latest_diagonal_index(triangle: Sequence[Sequence[Number]]) -> List[int]:
    """For each row, the development-age index of the latest observed cell."""
    out: List[int] = []
    for row in triangle:
        idx = -1
        for j, v in enumerate(row):
            if _is_obs(v):
                idx = j
        out.append(idx)
    return out


def project_triangle(
    triangle: Sequence[Sequence[Number]],
    selected: Sequence[float],
) -> List[List[float]]:
    """Fill in the lower-right of the triangle using selected age-to-age factors."""
    n_dev = len(triangle[0])
    projected: List[List[float]] = []
    for row in triangle:
        new_row: List[float] = []
        last_val: Optional[float] = None
        for j, v in enumerate(row):
            if _is_obs(v):
                new_row.append(float(v))
                last_val = float(v)
            else:
                if last_val is None:
                    new_row.append(float("nan"))
                else:
                    f = selected[j - 1] if (j - 1) < len(selected) else 1.0
                    last_val = last_val * float(f)
                    new_row.append(last_val)
        projected.append(new_row)
        _ = n_dev  # silence unused warning if any
    return projected


def chain_ladder(
    triangle: Sequence[Sequence[Number]],
    selected: Optional[Sequence[float]] = None,
    tail: float = 1.0,
    excluded: Optional[set] = None,
) -> ChainLadderResult:
    """Run the chain ladder and return all the bits the UI needs.

    If ``selected`` is omitted, volume-weighted factors are used.
    ``excluded`` is a set of (i, j) link-ratio coordinates to drop from
    the volume/simple averages — pass it from the UI to honour user toggles.
    """
    tri: List[List[Number]] = [list(r) for r in triangle]
    vol = volume_weighted_factors(tri, excluded=excluded)
    simp = simple_average_factors(tri, excluded=excluded)
    sel = [float(x) for x in (selected if selected is not None else vol)]
    ind = individual_link_ratios(tri)
    cdf = cumulative_dev_factors(sel, tail=tail)
    latest_vals = latest_diagonal_values(tri)
    latest_idx = latest_diagonal_index(tri)
    ultimates = [
        latest_vals[i] * cdf[latest_idx[i]] if latest_idx[i] >= 0 else 0.0
        for i in range(len(tri))
    ]
    ibnr = [ultimates[i] - latest_vals[i] for i in range(len(tri))]
    return ChainLadderResult(
        triangle=tri,
        volume_factors=vol,
        simple_factors=simp,
        selected_factors=sel,
        individual_factors=ind,
        cdf=cdf,
        latest_diagonal=latest_vals,
        ultimates=ultimates,
        ibnr=ibnr,
    )


@dataclass
class MackResult:
    """Output of Mack (1993) stochastic chain-ladder estimation."""
    sigma2: List[float]              # σ̂_j² per development period
    se_per_row: List[float]          # standard error of each ultimate
    cv_per_row: List[float]          # coefficient of variation (SE / Ultimate)
    se_total: float                  # SE of the sum of all ultimates
    cv_total: float                  # CV of the total ultimate


def _row_obs_through(row: Sequence[Number]) -> int:
    """Largest dev index j (0-based) where row[j] is observed; -1 if none."""
    last = -1
    for j, v in enumerate(row):
        if _is_obs(v):
            last = j
    return last


def mack_stats(
    triangle: Sequence[Sequence[Number]],
    selected: Sequence[float],
    excluded: Optional[set] = None,
) -> MackResult:
    """Mack's stochastic chain-ladder estimation errors.

    Implements the variance formulas from Mack (1993): "Distribution-free
    Calculation of the Standard Error of Chain Ladder Reserve Estimates"
    (ASTIN Bulletin 23). Returns per-row and total standard errors plus
    coefficients of variation.

    ``selected`` should be the same volume-weighted (or user-chosen)
    age-to-age factors used for the point-estimate projection. ``excluded``
    is the same set of (row, dev) coordinates honoured by the deterministic
    side of the model.
    """
    excluded = excluded or set()
    n = len(triangle)
    if n == 0 or len(triangle[0]) < 2:
        return MackResult([], [], [], 0.0, 0.0)
    m = len(triangle[0])
    f = [float(x) for x in selected]

    # σ̂_j² ----------------------------------------------------------------
    sigma2: List[float] = []
    for j in range(m - 1):
        used = []
        for i in range(n):
            if (i, j) in excluded:
                continue
            a, b = triangle[i][j], triangle[i][j + 1]
            if _is_obs(a) and _is_obs(b) and float(a) > 0:
                used.append((float(a), float(b) / float(a)))
        k = len(used)
        if k >= 2:
            s = sum(c * (ratio - f[j]) ** 2 for c, ratio in used)
            sigma2.append(s / (k - 1))
        else:
            # only one observation — defer; we'll backfill via the tail rule.
            sigma2.append(float("nan"))
    # Tail rule for the last column (Mack §3, eq. 5.14):
    # σ̂_{m-2}² = min(σ̂_{m-3}^4 / σ̂_{m-4}², σ̂_{m-3}², σ̂_{m-4}²)
    for j in range(m - 1):
        if not (sigma2[j] == sigma2[j] and not math.isnan(sigma2[j])):
            # build replacement from earlier valid sigmas
            valid = [s for s in sigma2[:j] if s == s and not math.isnan(s)]
            if len(valid) >= 2:
                a, b = valid[-1], valid[-2]
                sigma2[j] = min(a * a / b if b > 0 else a, a, b)
            elif len(valid) == 1:
                sigma2[j] = valid[-1]
            else:
                sigma2[j] = 0.0

    # Projected triangle (cumulative) -------------------------------------
    proj = project_triangle(triangle, f)

    # Column totals over rows where both C[k,j] and C[k,j+1] are observed
    # AND (k, j) is not excluded.
    S: List[float] = []
    for j in range(m - 1):
        tot = 0.0
        for i in range(n):
            if (i, j) in excluded:
                continue
            a, b = triangle[i][j], triangle[i][j + 1]
            if _is_obs(a) and _is_obs(b):
                tot += float(a)
        S.append(tot)

    # Per-row MSE ---------------------------------------------------------
    last_obs = [_row_obs_through(row) for row in triangle]
    ultimates = [proj[i][m - 1] for i in range(n)]
    mse_row: List[float] = [0.0] * n
    for i in range(n):
        I_i = last_obs[i]
        if I_i < 0 or I_i >= m - 1:
            continue  # nothing to project
        acc = 0.0
        for j in range(I_i, m - 1):
            if f[j] == 0 or S[j] == 0 or proj[i][j] == 0:
                continue
            acc += (sigma2[j] / (f[j] ** 2)) * (1.0 / proj[i][j] + 1.0 / S[j])
        mse_row[i] = (ultimates[i] ** 2) * acc

    se_row = [math.sqrt(v) if v > 0 else 0.0 for v in mse_row]
    cv_row = [se_row[i] / ultimates[i] if ultimates[i] else 0.0 for i in range(n)]

    # Total MSE (Mack eq. 5.15) ------------------------------------------
    mse_total = sum(mse_row)
    for i in range(n):
        if last_obs[i] < 0 or last_obs[i] >= m - 1:
            continue
        for k in range(i + 1, n):
            if last_obs[k] < 0 or last_obs[k] >= m - 1:
                continue
            j_lo = max(last_obs[i], last_obs[k])
            cross = 0.0
            for j in range(j_lo, m - 1):
                if f[j] == 0 or S[j] == 0:
                    continue
                cross += (sigma2[j] / (f[j] ** 2)) / S[j]
            mse_total += 2.0 * ultimates[i] * ultimates[k] * cross

    se_total = math.sqrt(mse_total) if mse_total > 0 else 0.0
    total_ult = sum(ultimates)
    cv_total = se_total / total_ult if total_ult else 0.0
    return MackResult(sigma2=sigma2, se_per_row=se_row, cv_per_row=cv_row,
                      se_total=se_total, cv_total=cv_total)


@dataclass
class Diagnostics:
    """Mack (1994) model-assumption diagnostics."""
    standardised_residuals: List[List[Optional[float]]]   # per (i, j)
    outliers: List[tuple]                                 # list of (i, j, residual)
    cy_z: float                                           # calendar-year sign-test Z
    cy_p_two_sided: float                                 # approx p-value
    indep_z: float                                        # Spearman independence Z
    indep_p_two_sided: float
    inflation_slope: float                                # slope of mean log-link-ratio vs i
    inflation_pvalue: float                               # two-sided p-value for slope


def _normal_two_sided_p(z: float) -> float:
    """Two-sided p-value for a standard-normal Z (no scipy dependency)."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def mack_diagnostics(
    triangle: Sequence[Sequence[Number]],
    selected: Sequence[float],
    excluded: Optional[set] = None,
    outlier_threshold: float = 2.0,
) -> Diagnostics:
    """Compute standardised residuals + classic Mack assumption tests.

    * Standardised residual:
          r[i,j] = (C[i,j+1] - f_j * C[i,j]) / (σ_j * sqrt(C[i,j]))
      Cells with |r| > ``outlier_threshold`` are flagged as outliers.

    * Calendar-year sign test (Tarbell): for each calendar diagonal, count
      link ratios "small" (< column median) vs "large" (>). Aggregate
      across diagonals and Z-score against Binomial(n, 0.5).

    * Independence / inflation test: weighted Spearman rank correlation
      between successive link-ratio columns (Mack 1994 §3).

    * Inflation trend: simple OLS slope of mean(ln(F[i,j])) on accident
      index i (positive slope ⇒ ratios drifting up over accident years).
    """
    excluded = excluded or set()
    n = len(triangle)
    m = len(triangle[0]) if triangle else 0
    f = [float(x) for x in selected]
    mack = mack_stats(triangle, selected, excluded=excluded)
    sigma = [math.sqrt(s) if s > 0 else 0.0 for s in mack.sigma2]

    # --- standardised residuals --------------------------------------
    resid: List[List[Optional[float]]] = []
    for i in range(n):
        row: List[Optional[float]] = []
        for j in range(m - 1):
            a, b = triangle[i][j], triangle[i][j + 1]
            if (i, j) not in excluded \
                    and _is_obs(a) and _is_obs(b) and float(a) > 0 \
                    and sigma[j] > 0:
                r = (float(b) - f[j] * float(a)) / (sigma[j] * math.sqrt(float(a)))
                row.append(r)
            else:
                row.append(None)
        resid.append(row)

    outliers = [(i, j, r) for i, row in enumerate(resid)
                for j, r in enumerate(row)
                if r is not None and abs(r) > outlier_threshold]

    # --- Calendar-year sign test -------------------------------------
    # Per-column median of link ratios; count "small" vs "large" along
    # each diagonal (i + j == d).
    indiv = individual_link_ratios(triangle)
    col_medians: List[Optional[float]] = []
    for j in range(m - 1):
        col = [indiv[i][j] for i in range(n)
               if indiv[i][j] is not None and (i, j) not in excluded]
        if col:
            s = sorted(col)
            mid = len(s) // 2
            med = s[mid] if len(s) % 2 == 1 else 0.5 * (s[mid - 1] + s[mid])
            col_medians.append(med)
        else:
            col_medians.append(None)

    s_count = 0
    e_count = 0.0
    var_count = 0.0
    for d in range(m - 1):
        # cells on diagonal d that are "valid" — not equal to median (Mack
        # drops ties so they don't bias the test).
        n_d = 0
        s_d = 0
        for i in range(n):
            j = d - i
            if 0 <= j < m - 1 and indiv[i][j] is not None \
                    and (i, j) not in excluded \
                    and col_medians[j] is not None \
                    and indiv[i][j] != col_medians[j]:
                n_d += 1
                if indiv[i][j] < col_medians[j]:
                    s_d += 1
        if n_d >= 1:
            s_count += s_d
            e_count += n_d / 2.0
            var_count += n_d / 4.0
    if var_count > 0:
        cy_z = (s_count - e_count) / math.sqrt(var_count)
    else:
        cy_z = 0.0
    cy_p = _normal_two_sided_p(cy_z)

    # --- Independence of dev factors (Spearman across adjacent columns) ---
    # Compute the rank correlation between (F[i,j])_i and (F[i,j+1])_i
    # for each j, restricted to rows where both are observed.
    def _ranks(xs):
        # Average-rank treatment of ties.
        order = sorted(range(len(xs)), key=lambda k: xs[k])
        ranks = [0.0] * len(xs)
        i = 0
        while i < len(xs):
            k = i
            while k + 1 < len(xs) and xs[order[k + 1]] == xs[order[i]]:
                k += 1
            avg = (i + k) / 2.0 + 1
            for q in range(i, k + 1):
                ranks[order[q]] = avg
            i = k + 1
        return ranks

    T_terms = []
    weights = []
    for j in range(m - 2):
        pairs = []
        for i in range(n):
            a, b = indiv[i][j], indiv[i][j + 1]
            if a is not None and b is not None \
                    and (i, j) not in excluded and (i, j + 1) not in excluded:
                pairs.append((a, b))
        I_j = len(pairs)
        if I_j < 3:
            continue
        a_ranks = _ranks([p[0] for p in pairs])
        b_ranks = _ranks([p[1] for p in pairs])
        d2 = sum((a_ranks[k] - b_ranks[k]) ** 2 for k in range(I_j))
        T_j = 1 - (6 * d2) / (I_j * (I_j ** 2 - 1))
        T_terms.append(T_j * (I_j - 1))
        weights.append(I_j - 1)
    if weights:
        T = sum(T_terms) / sum(weights)
        var_T = 1.0 / sum(weights)
        indep_z = T / math.sqrt(var_T) if var_T > 0 else 0.0
    else:
        indep_z = 0.0
    indep_p = _normal_two_sided_p(indep_z)

    # --- Inflation trend (mean log-link-ratio vs accident index) ----
    xs_ay = []
    ys_logf = []
    for i in range(n):
        ratios = [r for r in indiv[i] if r is not None and r > 0]
        if ratios:
            xs_ay.append(i)
            ys_logf.append(sum(math.log(r) for r in ratios) / len(ratios))
    if len(xs_ay) >= 3:
        mean_x = sum(xs_ay) / len(xs_ay)
        mean_y = sum(ys_logf) / len(ys_logf)
        sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs_ay, ys_logf))
        sxx = sum((x - mean_x) ** 2 for x in xs_ay)
        slope = sxy / sxx if sxx > 0 else 0.0
        # residual stderr → t-stat → approx p (use normal approximation)
        intercept = mean_y - slope * mean_x
        resid_var = sum(
            (y - (intercept + slope * x)) ** 2
            for x, y in zip(xs_ay, ys_logf)
        ) / max(1, len(xs_ay) - 2)
        se_slope = math.sqrt(resid_var / sxx) if sxx > 0 else 0.0
        if se_slope > 0:
            t = slope / se_slope
            inflation_p = _normal_two_sided_p(t)
        else:
            inflation_p = 1.0
    else:
        slope = 0.0
        inflation_p = 1.0

    return Diagnostics(
        standardised_residuals=resid,
        outliers=outliers,
        cy_z=cy_z, cy_p_two_sided=cy_p,
        indep_z=indep_z, indep_p_two_sided=indep_p,
        inflation_slope=slope, inflation_pvalue=inflation_p,
    )


def to_incremental(cumulative: Sequence[Sequence[Number]]) -> List[List[Number]]:
    """Convert a cumulative triangle to incremental.

    inc[i, 0]   = cum[i, 0]
    inc[i, j>0] = cum[i, j] - cum[i, j-1]   (when both observed)

    Unobserved cells stay unobserved.
    """
    out: List[List[Number]] = []
    for row in cumulative:
        new_row: List[Number] = []
        prev: Optional[float] = None
        for j, v in enumerate(row):
            if _is_obs(v):
                if j == 0 or prev is None:
                    new_row.append(float(v))
                else:
                    new_row.append(float(v) - prev)
                prev = float(v)
            else:
                new_row.append(None)
                # Don't reset prev — if a future cell becomes observed,
                # we still want the strictly-incremental interpretation.
        out.append(new_row)
    return out


def to_cumulative(incremental: Sequence[Sequence[Number]]) -> List[List[Number]]:
    """Convert an incremental triangle to cumulative.

    Running sum across each accident row, propagating None as unobserved.
    """
    out: List[List[Number]] = []
    for row in incremental:
        new_row: List[Number] = []
        running: Optional[float] = None
        for v in row:
            if _is_obs(v):
                running = (running or 0.0) + float(v)
                new_row.append(running)
            else:
                new_row.append(None)
        out.append(new_row)
    return out


def sample_triangle() -> List[List[Number]]:
    """A classic textbook triangle (Friedland-style cumulative paid)."""
    return [
        [1000.0, 1855.0, 2423.0, 2988.0, 3335.0, 3483.0, 3552.0, 3603.0, 3624.0, 3631.0],
        [1113.0, 2103.0, 2774.0, 3422.0, 3844.0, 4010.0, 4090.0, 4148.0, 4172.0, None],
        [1265.0, 2433.0, 3233.0, 3977.0, 4458.0, 4658.0, 4751.0, 4818.0, None,   None],
        [1490.0, 2873.0, 3880.0, 4598.0, 5152.0, 5400.0, 5508.0, None,   None,   None],
        [1725.0, 3261.0, 4351.0, 5323.0, 5969.0, 6249.0, None,   None,   None,   None],
        [1889.0, 3576.0, 4778.0, 5675.0, 6362.0, None,   None,   None,   None,   None],
        [2061.0, 3833.0, 5066.0, 6020.0, None,   None,   None,   None,   None,   None],
        [2255.0, 4146.0, 5552.0, None,   None,   None,   None,   None,   None,   None],
        [2415.0, 4506.0, None,   None,   None,   None,   None,   None,   None,   None],
        [2640.0, None,   None,   None,   None,   None,   None,   None,   None,   None],
    ]
