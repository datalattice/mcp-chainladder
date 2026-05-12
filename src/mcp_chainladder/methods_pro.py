"""Pro-tier additional reserving methods + interpretive analytics.

What's here:
  * `bornhuetter_ferguson` — BF reserving (Bornhuetter-Ferguson 1972)
  * `interpret_diagnostics` — Mack tests with verdict labels and
    plain-English summaries, ready for Claude to read back to the user
  * `sensitivity_analysis` — drop-one-out impact ranking on IBNR
  * `tail_extrapolation` — fit exponential or inverse-power tails to
    the late development factors

Future:
  * Cape Cod — derives the prior loss ratio from the triangle itself
  * Mack BF — Mack stochastic on a BF projection (Mack 2000)
  * GLM Tweedie — generalised linear model alternative
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from mcp_chainladder import chainladder as cl


@dataclass
class BornhuetterFergusonResult:
    """One BF projection, alongside everything needed to compare against the
    plain chain-ladder result."""
    a_priori_ultimates: list[float]   # input — expected ultimates by AY
    used_up_proportion: list[float]   # 1 / CDF[latest_idx], per AY
    bf_ultimates:       list[float]   # latest + (1 − used_up) · a_priori
    bf_ibnr:            list[float]   # bf_ultimates − latest
    cl_ultimates:       list[float]   # chain-ladder ultimates for comparison
    cl_ibnr:            list[float]
    total_bf_ultimate:  float
    total_bf_ibnr:      float
    total_cl_ultimate:  float
    total_cl_ibnr:      float


def bornhuetter_ferguson(
    triangle: list[list[float | None]],
    a_priori_ultimates: list[float],
    selected_factors: list[float] | None = None,
    tail: float = 1.0,
    excluded: set[tuple[int, int]] | None = None,
) -> BornhuetterFergusonResult:
    """Bornhuetter-Ferguson (1972) reserving method.

    Splits each accident year's ultimate into:
      • the bit that's already paid (latest diagonal) — "used up", and
      • an expected-pattern reserve = (1 − CDF⁻¹) × a-priori ultimate.

    The chain-ladder CDF tells us how much development is still to come
    for each AY; we apply (1 − used_up_proportion) of the a-priori
    ultimate as the IBNR estimate, then add the actually-paid latest
    diagonal to get the BF ultimate. Less sensitive to noisy late
    development than pure chain ladder — the canonical "second method"
    for benchmarking reserves.

    Args:
        triangle: Cumulative loss triangle, as in
            `chainladder.chain_ladder`.
        a_priori_ultimates: One expected ultimate per accident-year row.
            Often derived from an exposure × loss-ratio plan (e.g.,
            premium × expected loss ratio). Must have length `n_acc`.
        selected_factors: Override factor set; if omitted, the volume-
            weighted factors are used (same default as chain ladder).
        tail: Multiplicative tail factor.
        excluded: Outlier exclusions to honour.
    """
    excluded = excluded or set()
    n = len(triangle)
    if len(a_priori_ultimates) != n:
        raise ValueError(
            f"a_priori_ultimates length {len(a_priori_ultimates)} must "
            f"equal number of accident years {n}"
        )

    cl_result = cl.chain_ladder(
        triangle, selected=selected_factors, tail=tail, excluded=excluded,
    )
    latest_idx = cl.latest_diagonal_index(triangle)
    latest_vals = cl_result.latest_diagonal

    # used_up[i] = 1 / CDF[latest_idx[i]] — fraction of the ultimate that
    # we'd expect to have been observed by the latest diagonal.
    used_up: list[float] = []
    bf_ultimates: list[float] = []
    bf_ibnr: list[float] = []
    for i in range(n):
        idx = latest_idx[i]
        if idx < 0:
            used_up.append(0.0)
            bf_ultimates.append(float(a_priori_ultimates[i]))
            bf_ibnr.append(float(a_priori_ultimates[i]))
            continue
        cdf_i = cl_result.cdf[idx]
        u = 1.0 / cdf_i if cdf_i > 0 else 0.0
        ibnr_i = (1.0 - u) * float(a_priori_ultimates[i])
        used_up.append(u)
        bf_ibnr.append(ibnr_i)
        bf_ultimates.append(latest_vals[i] + ibnr_i)

    return BornhuetterFergusonResult(
        a_priori_ultimates=[float(x) for x in a_priori_ultimates],
        used_up_proportion=used_up,
        bf_ultimates=bf_ultimates,
        bf_ibnr=bf_ibnr,
        cl_ultimates=list(cl_result.ultimates),
        cl_ibnr=list(cl_result.ibnr),
        total_bf_ultimate=sum(bf_ultimates),
        total_bf_ibnr=sum(bf_ibnr),
        total_cl_ultimate=cl_result.total_ultimate,
        total_cl_ibnr=cl_result.total_ibnr,
    )


# ---------------------------------------------------------------------------
# Interpret diagnostics — verdict labels + plain-English summaries
# ---------------------------------------------------------------------------

@dataclass
class TestVerdict:
    """One test's verdict, ready for Claude to read aloud."""
    stat:    float
    p_value: float
    verdict: str            # "strong evidence" / "significant" / "borderline" / "no evidence"
    summary: str            # full English sentence
    recommendation: str     # what the user might do about it


def _verdict_band(p: float) -> str:
    if not math.isfinite(p):
        return "no evidence"
    if p < 0.005: return "strong evidence"
    if p < 0.05:  return "significant"
    if p < 0.10:  return "borderline"
    return "no evidence"


def interpret_diagnostics(
    triangle: list[list[float | None]],
    selected_factors: list[float],
    excluded: set[tuple[int, int]] | None = None,
    outlier_threshold: float = 2.0,
) -> dict[str, object]:
    """Run mack_diagnostics + label every result with a plain-English
    verdict and recommended action. The free-tier `mack_diagnostics`
    returns raw stats; this Pro variant adds interpretation so Claude
    can give the user a confidence-graded narrative.
    """
    excluded = excluded or set()
    d = cl.mack_diagnostics(
        triangle, selected_factors,
        excluded=excluded,
        outlier_threshold=outlier_threshold,
    )

    # Calendar-year (Tarbell) ------------------------------------------------
    cy_verdict = _verdict_band(d.cy_p_two_sided)
    cy = TestVerdict(
        stat=d.cy_z, p_value=d.cy_p_two_sided, verdict=cy_verdict,
        summary=(
            "Tarbell calendar-year sign test "
            f"(Z = {d.cy_z:.4f}, p = {d.cy_p_two_sided:.4f}): "
            + {
                "strong evidence":  "strong evidence of a calendar-year effect — link ratios on the same diagonal cluster systematically above or below the column median.",
                "significant":      "significant calendar-year effect.",
                "borderline":       "marginal calendar-year effect — interpret with caution.",
                "no evidence":      "no diagonal pattern; link ratios appear evenly distributed around each column median.",
            }[cy_verdict]
        ),
        recommendation={
            "strong evidence":  "Investigate whether a single inflation event or claims-handling change is hitting all open AYs at once. Consider a calendar-year-indexed adjustment factor or a Bornhuetter-Ferguson blend with an external prior.",
            "significant":      "Check for known shocks (cat events, legislative changes) on the strong diagonal. A BF projection is a sensible robustness benchmark.",
            "borderline":       "Worth a sanity check; usually not material at this strength.",
            "no evidence":      "No action required from this test.",
        }[cy_verdict],
    )

    # Independence (Spearman across adjacent columns) ------------------------
    indep_verdict = _verdict_band(d.indep_p_two_sided)
    indep = TestVerdict(
        stat=d.indep_z, p_value=d.indep_p_two_sided, verdict=indep_verdict,
        summary=(
            "Spearman rank-correlation between adjacent development columns "
            f"(Z = {d.indep_z:.4f}, p = {d.indep_p_two_sided:.4f}): "
            + {
                "strong evidence":  "strong evidence that successive link ratios are not independent — high-ratio AYs early stay high-ratio AYs late (or vice versa).",
                "significant":      "significant dependence between development columns.",
                "borderline":       "weak dependence; small samples often produce borderline Z values here.",
                "no evidence":      "successive link ratios appear independent, as Mack assumes.",
            }[indep_verdict]
        ),
        recommendation={
            "strong evidence":  "The Mack standard errors will understate true reserve variability. Consider a bootstrap or copula-based stochastic projection, not just Mack 1993.",
            "significant":      "Treat the Mack SE as a lower bound on uncertainty; pair it with a BF comparison.",
            "borderline":       "Not actionable unless the triangle is small (< 8 AYs) where this test has low power.",
            "no evidence":      "No action required from this test.",
        }[indep_verdict],
    )

    # Inflation slope -------------------------------------------------------
    infl_verdict = _verdict_band(d.inflation_pvalue)
    infl = TestVerdict(
        stat=d.inflation_slope, p_value=d.inflation_pvalue, verdict=infl_verdict,
        summary=(
            f"OLS slope of mean(ln link-ratio) on accident-year index "
            f"(β = {d.inflation_slope:.6f}, p = {d.inflation_pvalue:.3e}): "
            + {
                "strong evidence":  f"strong evidence of an accident-year trend in link ratios — link ratios drift by {math.exp(d.inflation_slope) - 1:+.2%} per AY on average.",
                "significant":      f"significant AY trend (~{math.exp(d.inflation_slope) - 1:+.2%} per AY).",
                "borderline":       f"weak AY trend (~{math.exp(d.inflation_slope) - 1:+.2%} per AY).",
                "no evidence":      "no accident-year trend; link ratios are stationary across AYs as Mack assumes.",
            }[infl_verdict]
        ),
        recommendation={
            "strong evidence":  "Weight recent AYs more heavily (e.g., volume-weight only the last 3–5 AYs) or fit a trend-adjusted GLM. A flat-weight chain ladder will be systematically biased.",
            "significant":      "Try a recent-years-only volume weighting and compare against the full-history result. Diverging answers signals a real trend.",
            "borderline":       "Spot-check by re-running on the last 5 AYs only; if the result is similar, no action needed.",
            "no evidence":      "No action required from this test.",
        }[infl_verdict],
    )

    # Outliers ---------------------------------------------------------------
    n_out = len(d.outliers)
    outlier_severity: str
    if n_out == 0:
        outlier_severity = "clean"
        outlier_summary = f"No cells exceed |residual| > {outlier_threshold}."
        outlier_action  = "No action required."
    else:
        max_abs = max(abs(r) for _, _, r in d.outliers)
        if max_abs >= 3:
            outlier_severity = "severe"
        elif max_abs >= 2.5:
            outlier_severity = "moderate"
        else:
            outlier_severity = "mild"
        outlier_summary = (
            f"{n_out} cell(s) flagged at |residual| > {outlier_threshold}; "
            f"largest |residual| = {max_abs:.2f}. "
            "First few: " +
            ", ".join(f"AY{i+1}·{j+1}→{j+2} ({r:+.2f}σ)" for i, j, r in d.outliers[:4])
        )
        outlier_action = (
            "Investigate the flagged cells — large claim, processing anomaly, or data error? "
            "If genuine outliers, run `compute_chain_ladder` with `excluded=[[row, dev], …]` "
            "and compare the IBNR delta. The Pro `sensitivity_analysis` tool ranks every "
            "link ratio by its IBNR impact for a faster scan."
        )

    # Overall summary -------------------------------------------------------
    flags = [v.verdict for v in (cy, indep, infl)]
    strong = sum(1 for f in flags if f == "strong evidence")
    significant = sum(1 for f in flags if f == "significant")
    if strong + significant == 0 and n_out == 0:
        overall = "Clean. All three Mack tests pass and no outliers — the chain-ladder projection is sound."
    elif strong > 0:
        overall = "Caution. " + str(strong) + " test(s) show strong evidence against a Mack assumption; consider a Bornhuetter-Ferguson cross-check and recent-years weighting before publishing."
    elif significant > 0:
        overall = "Borderline. " + str(significant) + " test(s) significant; the central estimate is probably fine but the SE understates true variability."
    elif n_out >= 3:
        overall = "Investigate. The assumption tests pass but multiple outliers were flagged — likely a few influential observations rather than a systemic issue."
    else:
        overall = "Mostly clean — minor flags only."

    return {
        "calendar_year":  {
            "stat": cy.stat, "p_value": cy.p_value,
            "verdict": cy.verdict, "summary": cy.summary,
            "recommendation": cy.recommendation,
        },
        "independence":   {
            "stat": indep.stat, "p_value": indep.p_value,
            "verdict": indep.verdict, "summary": indep.summary,
            "recommendation": indep.recommendation,
        },
        "inflation":      {
            "stat": infl.stat, "p_value": infl.p_value,
            "verdict": infl.verdict, "summary": infl.summary,
            "recommendation": infl.recommendation,
        },
        "outliers": {
            "count": n_out,
            "severity": outlier_severity,
            "summary":  outlier_summary,
            "recommendation": outlier_action,
            "items": [
                {"row": int(i), "dev": int(j), "residual": float(r)}
                for i, j, r in d.outliers
            ],
        },
        "overall": overall,
    }


# ---------------------------------------------------------------------------
# Sensitivity analysis — rank link ratios by IBNR impact
# ---------------------------------------------------------------------------

def sensitivity_analysis(
    triangle: list[list[float | None]],
    selected_factors: list[float] | None = None,
    tail: float = 1.0,
    excluded: set[tuple[int, int]] | None = None,
    top_n: int = 10,
) -> dict[str, object]:
    """Drop each observable link ratio one-at-a-time and re-run the chain
    ladder. Returns the link ratios ranked by absolute IBNR impact so
    the actuary can see, at a glance, which observations are driving
    the projection.

    This is a brute-force leave-one-out — O(n_acc · n_dev) chain-ladder
    runs. For 10×10 that's ~100 fast invocations (well under a second
    on commodity hardware). Larger triangles may need the optional
    `top_n` cap to keep the response payload small.
    """
    excluded = excluded or set()
    n = len(triangle)
    m = len(triangle[0]) if triangle else 0
    baseline = cl.chain_ladder(
        triangle, selected=selected_factors, tail=tail, excluded=excluded,
    )
    baseline_ibnr = baseline.total_ibnr

    individual = cl.individual_link_ratios(triangle)
    deltas: list[dict[str, object]] = []
    for i in range(n):
        for j in range(m - 1):
            ratio = individual[i][j]
            if ratio is None:
                continue
            if (i, j) in excluded:
                continue
            trial_excluded = excluded | {(i, j)}
            trial = cl.chain_ladder(
                triangle,
                selected=selected_factors,
                tail=tail,
                excluded=trial_excluded,
            )
            delta = trial.total_ibnr - baseline_ibnr
            deltas.append({
                "row":           i,
                "dev":           j,
                "ratio":         float(ratio),
                "ibnr_with_excluded":   float(trial.total_ibnr),
                "ibnr_delta":           float(delta),
                "ibnr_delta_pct":       float(delta / baseline_ibnr) if baseline_ibnr else 0.0,
            })

    # Sort by absolute IBNR delta, descending.
    deltas.sort(key=lambda x: abs(float(x["ibnr_delta"])), reverse=True)
    top = deltas[: max(1, top_n)]

    return {
        "baseline_ibnr": float(baseline_ibnr),
        "n_tested":      len(deltas),
        "top_influential": top,
        "summary": (
            f"Tested {len(deltas)} link ratios. "
            + (
                "The top influence is "
                f"AY{top[0]['row']+1}·{top[0]['dev']+1}→{top[0]['dev']+2} "
                f"(ratio {top[0]['ratio']:.4f}); excluding it would move "
                f"total IBNR by {top[0]['ibnr_delta']:+,.0f} "
                f"({top[0]['ibnr_delta_pct']:+.2%})."
                if top else
                "No observable link ratios to test."
            )
        ),
    }


# ---------------------------------------------------------------------------
# Tail extrapolation — fit a parametric tail to the late development factors
# ---------------------------------------------------------------------------

@dataclass
class TailFit:
    """One candidate parametric fit of the development tail."""
    model:        str           # "exponential" | "inverse_power" | "geometric_decay"
    parameters:   dict[str, float]
    r_squared:    float
    extrapolated: list[float]   # additional factors beyond the observed periods
    tail_factor:  float         # product of all extrapolated factors


def tail_extrapolation(
    selected_factors: list[float],
    n_extra: int = 6,
) -> dict[str, object]:
    """Fit two parametric models to the late development factors and
    extrapolate forward by `n_extra` periods. Returns both fits plus a
    recommendation for which to use.

    Models:
      • Exponential decay: ln(f_j - 1) = a + b·j  (linear regression)
      • Inverse-power:     ln(f_j - 1) = a + b·ln(j+1)

    The best-fit (higher R²) gets the recommendation flag. Both
    produce a multiplicative tail factor = product of extrapolated f_j
    that the user can plug back into `compute_chain_ladder(tail=…)`.
    """
    # Take only factors strictly above 1 — log(f - 1) needs positivity.
    pairs = [(j + 1, f) for j, f in enumerate(selected_factors) if f > 1.0]
    if len(pairs) < 3:
        return {
            "error": "Need at least 3 development factors above 1.0 to fit a tail.",
            "fits": [],
        }

    xs_lin = [float(j) for j, _ in pairs]
    ys_log = [math.log(f - 1) for _, f in pairs]

    exp_fit  = _fit_loglinear(xs_lin, ys_log)
    pow_fit  = _fit_loglinear([math.log(x) for x in xs_lin], ys_log)

    n_obs = len(selected_factors)

    def extrapolate(fit: tuple[float, float], inverse_power: bool) -> tuple[list[float], float]:
        a, b = fit
        out: list[float] = []
        for k in range(1, n_extra + 1):
            j = n_obs + k                     # 1-based dev index of the new factor
            x = math.log(j) if inverse_power else float(j)
            f_minus_1 = math.exp(a + b * x)
            out.append(1.0 + f_minus_1)
        return out, math.prod(out)

    exp_extra, exp_tail = extrapolate(exp_fit[:2], inverse_power=False)
    pow_extra, pow_tail = extrapolate(pow_fit[:2], inverse_power=True)

    fits: list[TailFit] = [
        TailFit(
            model="exponential",
            parameters={"a": exp_fit[0], "b": exp_fit[1]},
            r_squared=exp_fit[2],
            extrapolated=exp_extra,
            tail_factor=exp_tail,
        ),
        TailFit(
            model="inverse_power",
            parameters={"a": pow_fit[0], "b": pow_fit[1]},
            r_squared=pow_fit[2],
            extrapolated=pow_extra,
            tail_factor=pow_tail,
        ),
    ]
    recommended = max(fits, key=lambda f: f.r_squared).model

    return {
        "fits": [
            {
                "model": f.model,
                "parameters":   f.parameters,
                "r_squared":    f.r_squared,
                "extrapolated": f.extrapolated,
                "tail_factor":  f.tail_factor,
            }
            for f in fits
        ],
        "recommended": recommended,
        "summary": (
            f"Recommended model: {recommended} (R² = "
            f"{max(f.r_squared for f in fits):.4f}). "
            f"Implied tail factor = "
            f"{next(f.tail_factor for f in fits if f.model == recommended):.6f} "
            f"over the next {n_extra} dev periods."
        ),
    }


def _fit_loglinear(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Plain OLS in (xs, ys). Returns (intercept, slope, R²)."""
    n = len(xs)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return mean_y, 0.0, 0.0
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return intercept, slope, r2


# ---------------------------------------------------------------------------
# Compare methods — CL vs BF side-by-side
# ---------------------------------------------------------------------------

def compare_methods(
    triangle: list[list[float | None]],
    a_priori_ultimates: list[float],
    selected_factors: list[float] | None = None,
    tail: float = 1.0,
    excluded: set[tuple[int, int]] | None = None,
) -> dict[str, object]:
    """Run chain ladder and Bornhuetter-Ferguson side-by-side and report
    where they agree vs diverge. The single most useful "second opinion"
    move an actuary makes."""
    cl_result = cl.chain_ladder(
        triangle, selected=selected_factors, tail=tail, excluded=excluded or set(),
    )
    bf_result = bornhuetter_ferguson(
        triangle, a_priori_ultimates,
        selected_factors=selected_factors,
        tail=tail,
        excluded=excluded,
    )

    # Largest divergence by AY (BF ult − CL ult).
    diffs = [
        bf_result.bf_ultimates[i] - cl_result.ultimates[i]
        for i in range(cl_result.n_acc)
    ]
    max_div = max(diffs, key=abs, default=0.0)
    max_div_idx = diffs.index(max_div) if diffs else -1

    return {
        "chain_ladder": {
            "ultimates":     cl_result.ultimates,
            "ibnr":          cl_result.ibnr,
            "total_ultimate": cl_result.total_ultimate,
            "total_ibnr":     cl_result.total_ibnr,
        },
        "bornhuetter_ferguson": {
            "ultimates":     bf_result.bf_ultimates,
            "ibnr":          bf_result.bf_ibnr,
            "total_ultimate": bf_result.total_bf_ultimate,
            "total_ibnr":     bf_result.total_bf_ibnr,
        },
        "diffs_by_ay": diffs,
        "total_diff_ultimate": bf_result.total_bf_ultimate - cl_result.total_ultimate,
        "total_diff_ibnr":     bf_result.total_bf_ibnr     - cl_result.total_ibnr,
        "largest_divergence": {
            "ay":         max_div_idx + 1 if max_div_idx >= 0 else None,
            "diff":       max_div,
            "interpretation": (
                "Methods diverge most at AY "
                f"{max_div_idx + 1}: BF − CL = {max_div:+,.0f}. "
                + (
                    "BF is higher → CL may be projecting too aggressively."
                    if max_div > 0
                    else "BF is lower → CL may be under-reserving."
                    if max_div < 0
                    else "Methods agree exactly."
                )
            ) if diffs else "No accident years to compare.",
        },
    }
