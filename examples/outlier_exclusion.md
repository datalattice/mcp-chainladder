# Example — diagnostics + outlier exclusion

> Diagnostics-driven robustness checking with the chain ladder.

**Me:**
> Use the textbook triangle. Run the diagnostics and tell me whether
> there's anything I should worry about.

**Claude** *(calls `sample_triangle` then `mack_diagnostics`)*:
> Three tests + a residual scan on the textbook triangle:
>
> | Test | Stat | p-value | Verdict |
> |---|---|---|---|
> | Calendar-year (Tarbell) | Z = 0.0 | 1.000 | No evidence |
> | Independence (Spearman) | Z = −0.35 | 0.726 | No evidence |
> | Inflation slope | β = 0.053 | 1.3e-12 | **Strong evidence** |
>
> No cells exceed |2σ| on the residual scan.
>
> The inflation finding is the actionable one: the mean log-link-ratio
> drifts upward by ~5%/AY, which violates Mack's homogeneity
> assumption. Weighting recent years more (or fitting a separate
> trend) would tighten the IBNR estimate. The other two tests are
> clean.

**Me:**
> Just hypothetically — what if I excluded AY 3 at dev 2→3? Show me
> the before-and-after on the IBNR.

**Claude** *(calls `compute_chain_ladder` twice — once baseline, once
with `excluded=[[2, 1]]`)*:
> | Total | Baseline | Excluded (2,1) | Δ |
> |---|---:|---:|---:|
> | Ultimate | 65,883.37 | 65,847.04 | −36.33 |
> | IBNR     | 16,425.37 | 16,389.04 | −36.33 |
>
> Volume factor at 2→3 moves from 1.3313 to 1.3275. The change is
> small enough to count as a robustness check passing rather than a
> finding — the triangle isn't sensitive to dropping that single
> ratio.
