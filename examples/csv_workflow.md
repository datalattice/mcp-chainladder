# Example — load a CSV and produce a reserving estimate

> End-to-end with a real file on disk.

**Setup:** save the following as `~/Desktop/motor_2026q1.csv`. The
parser tolerates the `Title`/`LOB` metadata rows up top, the `Dev N`
header, and the empty cells in the lower-right.

```csv
Product,Chain Ladder
Disclaimer,For calculation only — not actuarial advice.

Title,2026 Q1 Motor
LOB,Motor
Currency,USD

Cumulative triangle
,Dev 1,Dev 2,Dev 3,Dev 4,Dev 5,Dev 6
AY 1,"1,000",1855,2423,2988,3335,3483
AY 2,1113,2103,2774,3422,3844,
AY 3,1265,2433,3233,3977,,
AY 4,1490,2873,3880,,,
AY 5,1725,3261,,,,
AY 6,1889,,,,,
```

**Me:**
> Load `~/Desktop/motor_2026q1.csv`, run the chain ladder, and give me
> the per-AY ultimates and IBNR. Also flag any diagnostic concerns.

**Claude** *(calls `parse_csv_triangle`, `compute_chain_ladder`,
`mack_diagnostics` in sequence, then synthesises)*:
> Loaded a 6×6 cumulative triangle from `motor_2026q1.csv`.
>
> | AY | Latest | Ultimate | IBNR |
> |---|---:|---:|---:|
> | 1 | 3,483 | 3,483 | 0 |
> | 2 | 3,844 | 3,995 | 151 |
> | 3 | 3,977 | 4,338 | 361 |
> | 4 | 3,880 | 4,712 | 832 |
> | 5 | 3,261 | 5,247 | 1,986 |
> | 6 | 1,889 | 5,853 | 3,964 |
> | **Total** | **20,334** | **27,628** | **7,294** |
>
> Diagnostics on the 6×6 triangle: only 5 link ratios per dev period,
> so the calendar-year and independence tests have very wide CIs —
> p-values 0.41 and 0.62 respectively. No statistical concern, but
> also not statistically clean; treat the result as a directional
> indicator that needs an actuarial gut-check rather than a
> production reserve.

> ⚠ Disclaimer: This is a mechanical chain-ladder calculation. Final
> reserves require qualified actuarial judgement.
