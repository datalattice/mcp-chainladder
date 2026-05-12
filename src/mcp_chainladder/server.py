"""MCP server exposing actuarial chain-ladder tools.

Every tool wraps a function from `chainladder.py` and returns plain Python
dicts/lists, which the MCP SDK auto-serialises to JSON for the client.
Tool descriptions and parameter docstrings are written for Claude (and
other LLM clients) to read — be explicit about units, conventions, and
when each tool is the right one.

Conventions used throughout:

  * `triangle` is `list[list[float | None]]` — outer index is the
    accident-year row (oldest first), inner index is the development
    period (0 ≡ first dev age). `None` ≡ unobserved (lower-right of a
    classic cumulative triangle).
  * Factors are returned in development-period order: factor[j] is the
    age-to-age factor going from dev j+1 to dev j+2.
  * `excluded` (when accepted) is a list of `[row_i, dev_j]` pairs
    identifying individual link ratios to drop from the volume / simple
    averages — the standard outlier-exclusion mechanism.
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_chainladder import chainladder as cl
from mcp_chainladder import methods_pro
from mcp_chainladder.license import check_pro_license, require_pro_or_explain


mcp = FastMCP(
    "chainladder",
    instructions=(
        "Actuarial chain-ladder reserving tools for cumulative loss "
        "triangles. Use `compute_chain_ladder` for the end-to-end "
        "projection (factors → CDF → ultimates → IBNR). Use "
        "`mack_stochastic` for Mack (1993) standard errors. Use "
        "`mack_diagnostics` for the calendar-year sign test, Spearman "
        "independence, inflation trend, and outlier detection. "
        "`parse_csv_triangle` parses a CSV file into a triangle. "
        "`sample_triangle` returns the classic textbook 10×10 example "
        "for demos. Pass triangle cells as numbers or null; null means "
        "unobserved (lower-right of a cumulative triangle)."
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _excluded_to_set(excluded: list[list[int]] | None) -> set[tuple[int, int]]:
    """Convert a wire-format `[[row, dev], …]` to the internal set of tuples
    the math layer expects."""
    if not excluded:
        return set()
    return {(int(c[0]), int(c[1])) for c in excluded if len(c) == 2}


# Disclaimer attached to every tool's result so the language model always
# has it in context when relaying numbers to the user. Mirrors the LICENSE
# file's actuarial-use clause and the desktop app's persistent footer.
DISCLAIMER = (
    "Calculation only — not actuarial advice. Selection of data, factors, "
    "tails, exclusions, and the interpretation of stochastic error "
    "measures require professional judgement by a qualified actuary, who "
    "remains solely responsible for the use and onward reliance on these "
    "outputs and for compliance with applicable professional standards "
    "and regulation."
)


def _with_disclaimer(payload: dict[str, Any]) -> dict[str, Any]:
    """Tag every tool response with the actuarial-use disclaimer.

    Doesn't overwrite an existing `disclaimer` key — if a tool already
    set one (e.g., on a license-error envelope), we leave it untouched
    and surface the actuarial disclaimer under a separate key. This
    keeps Pro-license errors readable while still always reminding the
    consumer that this is a calculation tool.
    """
    if "disclaimer" in payload:
        return {**payload, "actuarial_disclaimer": DISCLAIMER}
    return {**payload, "disclaimer": DISCLAIMER}


def _serialise_individual(matrix: list[list[float | None]]) -> list[list[float | None]]:
    """Identity pass — kept as a function so the JSON shape is documented
    in one place. None entries stay None on the wire (Claude sees `null`)."""
    return [[None if v is None else float(v) for v in row] for row in matrix]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def compute_chain_ladder(
    triangle: list[list[float | None]],
    selected_factors: list[float] | None = None,
    tail: float = 1.0,
    excluded: list[list[int]] | None = None,
) -> dict[str, Any]:
    """Run a full chain-ladder reserving calculation on a cumulative loss
    triangle. This is the workhorse tool — call it whenever the user asks
    "what's the IBNR?", "what does the chain ladder say?", or hands you a
    triangle and asks for projections.

    Args:
        triangle: Cumulative loss triangle as a list of lists. Outer index
            is the accident-year row (oldest first). Inner index is the
            development period (0 = first age). Cells are numbers or null;
            null means unobserved (typical lower-right corner of a real
            triangle). All rows should be the same length — pad with
            trailing nulls if needed.
        selected_factors: Optional list of user-chosen age-to-age factors,
            one per development-period transition (length = n_dev - 1).
            When omitted, the volume-weighted factors derived from the
            triangle are used as the selected set.
        tail: Multiplicative tail factor applied beyond the last
            development period. Default 1.0 (no tail).
        excluded: List of `[row_i, dev_j]` pairs identifying individual
            link ratios to drop from the volume and simple averages. Use
            this for outlier handling — typically after consulting
            `mack_diagnostics` to find suspect cells.

    Returns:
        A dictionary containing:
          - `volume_factors`: list[float] — volume-weighted age-to-age
          - `simple_factors`: list[float] — simple average of link ratios
          - `selected_factors`: list[float] — the set actually used
          - `individual_factors`: list[list[float | None]] — per-row link
            ratios C[i, j+1] / C[i, j]; null where the pair is unobserved
          - `cdf`: list[float] — cumulative dev factors to ultimate; last
            element is `tail`
          - `latest_diagonal`: list[float] — most recent observed value per
            accident row
          - `ultimates`: list[float] — projected ultimate per accident row
          - `ibnr`: list[float] — Ultimate − Latest, per accident row
          - `total_latest`, `total_ultimate`, `total_ibnr`: float scalars
          - `n_acc`, `n_dev`: int — triangle dimensions for convenience
    """
    excluded_set = _excluded_to_set(excluded)
    r = cl.chain_ladder(
        triangle,
        selected=selected_factors,
        tail=float(tail),
        excluded=excluded_set,
    )
    return _with_disclaimer({
        "volume_factors":     [float(x) for x in r.volume_factors],
        "simple_factors":     [float(x) for x in r.simple_factors],
        "selected_factors":   [float(x) for x in r.selected_factors],
        "individual_factors": _serialise_individual(r.individual_factors),
        "cdf":                [float(x) for x in r.cdf],
        "latest_diagonal":    [float(x) for x in r.latest_diagonal],
        "ultimates":          [float(x) for x in r.ultimates],
        "ibnr":               [float(x) for x in r.ibnr],
        "total_latest":       float(r.total_latest),
        "total_ultimate":     float(r.total_ultimate),
        "total_ibnr":         float(r.total_ibnr),
        "n_acc":              r.n_acc,
        "n_dev":              r.n_dev,
    })


@mcp.tool()
def project_triangle(
    triangle: list[list[float | None]],
    selected_factors: list[float],
) -> dict[str, Any]:
    """Fill the lower-right (unobserved) cells of a cumulative triangle
    using the supplied age-to-age factors.

    Args:
        triangle: As in `compute_chain_ladder`.
        selected_factors: One factor per development-period transition.
            Length must be `n_dev - 1`.

    Returns a dict with:
        - `triangle`: 2-D list of floats, same shape as the input, with
          unobserved cells filled in by chain-ladder projection. Rows
          with no observation contain `nan` for the projected cells.
        - `disclaimer`: standard actuarial-use disclaimer.
    """
    proj = cl.project_triangle(triangle, selected_factors)
    return _with_disclaimer({
        "triangle": [[float(v) for v in row] for row in proj],
    })


@mcp.tool()
def mack_stochastic(
    triangle: list[list[float | None]],
    selected_factors: list[float],
    excluded: list[list[int]] | None = None,
) -> dict[str, Any]:
    """Mack (1993) stochastic chain-ladder error estimation. Returns
    distribution-free standard errors and coefficients of variation
    per accident row plus the totals — the canonical sensitivity check
    for a deterministic chain-ladder result.

    Use this when the user asks about uncertainty, reserve risk, or
    confidence intervals. Pair it with `compute_chain_ladder` (use the
    same `selected_factors` for consistency).

    Args:
        triangle: As in `compute_chain_ladder`.
        selected_factors: The factors used for the point-estimate
            projection. Length = `n_dev - 1`.
        excluded: Outlier exclusions to honour, same shape as in
            `compute_chain_ladder`.

    Returns:
        - `sigma2`: list[float] — σ̂_j² per development period; backfilled
          via Mack's tail rule when only one observation is available
        - `se_per_row`: list[float] — standard error of each ultimate
        - `cv_per_row`: list[float] — coefficient of variation (SE /
          Ultimate) per accident row
        - `se_total`: float — SE of the sum of all ultimates (includes
          cross-row covariance per Mack eq. 5.15)
        - `cv_total`: float — CV of the total ultimate
    """
    excluded_set = _excluded_to_set(excluded)
    m = cl.mack_stats(triangle, selected_factors, excluded=excluded_set)
    return _with_disclaimer({
        "sigma2":     [float(x) for x in m.sigma2],
        "se_per_row": [float(x) for x in m.se_per_row],
        "cv_per_row": [float(x) for x in m.cv_per_row],
        "se_total":   float(m.se_total),
        "cv_total":   float(m.cv_total),
    })


@mcp.tool()
def mack_diagnostics(
    triangle: list[list[float | None]],
    selected_factors: list[float],
    excluded: list[list[int]] | None = None,
    outlier_threshold: float = 2.0,
) -> dict[str, Any]:
    """Mack (1994) assumption diagnostics — three statistical tests plus
    standardised-residual outlier detection. Use when the user asks
    "does the chain ladder look OK?", "are there any outliers?", or
    "should I be worried about [calendar-year / inflation / dependence]
    effects?".

    Args:
        triangle: As in `compute_chain_ladder`.
        selected_factors: Length-(n_dev - 1) factor set.
        excluded: Outlier exclusions to honour.
        outlier_threshold: Absolute standardised-residual threshold for
            flagging an outlier. Default 2.0 (the Tk app's default).

    Returns:
        - `standardised_residuals`: list[list[float | null]] — per-cell
          residual `r[i,j] = (C[i,j+1] − f_j·C[i,j]) / (σ_j·√C[i,j])`;
          null where the cell is excluded or the pair is unobserved
        - `outliers`: list of `{row: int, dev: int, residual: float}` —
          cells with `|residual| > outlier_threshold`
        - `calendar_year`: `{z: float, p_two_sided: float}` — Tarbell
          sign test for calendar-year effects (large |z| ⇒ suspect)
        - `independence`: `{z: float, p_two_sided: float}` — Spearman
          rank-correlation between adjacent development columns (large
          |z| ⇒ link ratios are not independent)
        - `inflation`: `{slope: float, p_value: float}` — OLS slope of
          mean(ln link-ratio) on accident-year index (non-zero ⇒
          accident-year trend in link ratios)

    Verdict guidance for translating p-values to plain English:
      p < 0.005 → "strong evidence"; p < 0.05 → "significant";
      p < 0.10  → "borderline";     p ≥ 0.10 → "no evidence".
    """
    excluded_set = _excluded_to_set(excluded)
    d = cl.mack_diagnostics(
        triangle, selected_factors,
        excluded=excluded_set,
        outlier_threshold=float(outlier_threshold),
    )
    return _with_disclaimer({
        "standardised_residuals": _serialise_individual(d.standardised_residuals),
        "outliers": [
            {"row": int(i), "dev": int(j), "residual": float(r)}
            for (i, j, r) in d.outliers
        ],
        "calendar_year": {
            "z":           float(d.cy_z),
            "p_two_sided": float(d.cy_p_two_sided),
        },
        "independence": {
            "z":           float(d.indep_z),
            "p_two_sided": float(d.indep_p_two_sided),
        },
        "inflation": {
            "slope":   float(d.inflation_slope),
            "p_value": float(d.inflation_pvalue),
        },
    })


@mcp.tool()
def parse_csv_triangle(path: str) -> dict[str, Any]:
    """Parse a CSV file from disk into a cumulative loss triangle.

    Reads the file, treats empty cells and the tokens "NA", "N/A", "NaN",
    "-" as unobserved, strips embedded commas (thousand separators), and
    drops any leading row whose first cell is non-numeric but whose
    remaining cells are mostly numeric (e.g. a "Dev 1, Dev 2, …" header).
    Auto-pads jagged rows to a rectangle with nulls.

    Use this when the user gives you a CSV file path and wants to run
    the chain ladder on it.

    Args:
        path: Absolute or `~`-relative path to the CSV file. Must be
            readable by the server process.

    Returns:
        - `triangle`: list[list[float | null]] — parsed cells, ready to
          pass to `compute_chain_ladder`
        - `n_acc`: int — number of accident-year rows
        - `n_dev`: int — number of development periods (max row length)
        - `source`: str — absolute path actually read
    """
    import csv
    import os

    abs_path = os.path.expanduser(path)
    rows: list[list[float | None]] = []
    with open(abs_path, "r", newline="") as fh:
        reader = csv.reader(fh)
        for raw in reader:
            cells = [_parse_cell(c) for c in raw]
            if not cells:
                continue
            # Drop rows where every cell is None (blank lines, header
            # strips, metadata key/value rows).
            if not any(c is not None for c in cells):
                continue
            # If the first cell is None but later cells aren't, treat as
            # a row-labelled data row ("AY 1, 1000, 1855, …") — drop the
            # leading label cell so we end up with pure data.
            if cells[0] is None and any(c is not None for c in cells[1:]):
                rows.append(cells[1:])
            else:
                rows.append(cells)

    if not rows:
        return _with_disclaimer({
            "triangle": [],
            "n_acc": 0,
            "n_dev": 0,
            "source": abs_path,
        })

    max_cols = max(len(r) for r in rows)
    padded: list[list[float | None]] = [
        r + [None] * (max_cols - len(r)) for r in rows
    ]
    return _with_disclaimer({
        "triangle": padded,
        "n_acc": len(padded),
        "n_dev": max_cols,
        "source": abs_path,
    })


def _parse_cell(s: str) -> float | None:
    """Wire-format cell parser shared by parse_csv_triangle. Empty / "NA"
    / "NaN" / "-" → None; everything else → float (commas stripped)."""
    if s is None:
        return None
    t = s.strip()
    if not t:
        return None
    low = t.lower()
    if low in ("nan", "na", "n/a", "-", "null", "none"):
        return None
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return None


@mcp.tool()
def to_incremental(
    cumulative: list[list[float | None]],
) -> dict[str, Any]:
    """Convert a cumulative triangle to incremental (per-period) values.

    `inc[i, 0]   = cum[i, 0]`
    `inc[i, j>0] = cum[i, j] - cum[i, j-1]` (when both observed)

    Unobserved cells stay unobserved.

    Args:
        cumulative: Cumulative triangle, possibly with unobserved cells.

    Returns dict with `triangle` (incremental, same shape) and the
    standard disclaimer.
    """
    return _with_disclaimer({"triangle": cl.to_incremental(cumulative)})


@mcp.tool()
def to_cumulative(
    incremental: list[list[float | None]],
) -> dict[str, Any]:
    """Convert an incremental triangle to cumulative (running sum per
    row). Unobserved cells propagate as null. Inverse of
    `to_incremental` on observed cells.

    Args:
        incremental: Incremental triangle.

    Returns dict with `triangle` (cumulative, same shape) and the
    standard disclaimer.
    """
    return _with_disclaimer({"triangle": cl.to_cumulative(incremental)})


# ---------------------------------------------------------------------------
# Pro-tier tools (gated by license check)
# ---------------------------------------------------------------------------

@mcp.tool()
def pro_license_status() -> dict[str, Any]:
    """Inspect the current Pro-tier license state. Returns whether Pro
    tools are unlocked, the registered owner, an expiry date if any,
    and a human-readable message that Claude can relay to the user.
    Free to call regardless of license state.

    Returns:
        - `active`: bool — whether the license is currently valid
        - `owner`: str | null — email associated with the license
        - `expires`: int | null — unix-epoch seconds, null = perpetual
        - `message`: str — plain-English status (great for Claude to
          read back to the user)
        - `upgrade_url`: str — where to buy / renew
    """
    return _with_disclaimer(check_pro_license().to_dict())


@mcp.tool()
def bornhuetter_ferguson(
    triangle: list[list[float | None]],
    a_priori_ultimates: list[float],
    selected_factors: list[float] | None = None,
    tail: float = 1.0,
    excluded: list[list[int]] | None = None,
) -> dict[str, Any]:
    """Bornhuetter-Ferguson (1972) reserving method. **Pro tier.**

    Combines the chain-ladder development pattern with an externally-
    provided a-priori ultimate per accident year, giving a result that
    is far less sensitive to noisy late development than pure chain
    ladder. The canonical "second method" for benchmarking reserves —
    when chain-ladder and BF agree, you can publish with confidence;
    when they diverge, the divergence is the finding.

    Args:
        triangle: Cumulative loss triangle, same shape as
            `compute_chain_ladder`.
        a_priori_ultimates: Expected ultimate per accident-year row,
            usually derived from `premium × expected loss ratio` or
            a plan figure. Must have length `n_acc`.
        selected_factors: Override factor set; defaults to volume-
            weighted (same default as chain ladder).
        tail: Multiplicative tail factor. Default 1.0.
        excluded: Outlier exclusions, same shape as in
            `compute_chain_ladder`.

    Returns either:
        - On success: `{a_priori_ultimates, used_up_proportion,
          bf_ultimates, bf_ibnr, cl_ultimates, cl_ibnr,
          total_bf_ultimate, total_bf_ibnr, total_cl_ultimate,
          total_cl_ibnr}` — note the chain-ladder values are returned
          alongside so the user can see the two methods side-by-side.
        - On license failure: `{error, status}` with status giving the
          upgrade URL and reason. Free-tier callers get this and can
          still see the API shape; no compute happens.
    """
    blocked = require_pro_or_explain()
    if blocked is not None:
        return blocked

    excluded_set = _excluded_to_set(excluded)
    result = methods_pro.bornhuetter_ferguson(
        triangle,
        a_priori_ultimates,
        selected_factors=selected_factors,
        tail=float(tail),
        excluded=excluded_set,
    )
    return _with_disclaimer({
        "a_priori_ultimates": result.a_priori_ultimates,
        "used_up_proportion": result.used_up_proportion,
        "bf_ultimates":       result.bf_ultimates,
        "bf_ibnr":            result.bf_ibnr,
        "cl_ultimates":       result.cl_ultimates,
        "cl_ibnr":            result.cl_ibnr,
        "total_bf_ultimate":  result.total_bf_ultimate,
        "total_bf_ibnr":      result.total_bf_ibnr,
        "total_cl_ultimate":  result.total_cl_ultimate,
        "total_cl_ibnr":      result.total_cl_ibnr,
    })


@mcp.tool()
def interpret_diagnostics(
    triangle: list[list[float | None]],
    selected_factors: list[float],
    excluded: list[list[int]] | None = None,
    outlier_threshold: float = 2.0,
) -> dict[str, Any]:
    """Run Mack assumption diagnostics + label each result with a plain-
    English verdict and a recommended action. **Pro tier.**

    Free-tier `mack_diagnostics` returns raw Z-scores and p-values; this
    Pro variant adds:

      • verdict band ("strong evidence" / "significant" / "borderline" /
        "no evidence") for each test, using the standard p-value cutoffs
      • a one-paragraph summary written so Claude can read it back to
        the user without further interpretation
      • a specific recommended action for each finding ("try BF",
        "weight recent years only", "investigate cells X, Y, Z", …)
      • an overall verdict pulling the three tests + outlier scan
        together into a single sentence

    Use this when the user asks "is the chain ladder OK?", "should I
    publish this?", or "what does the model tell me about itself?".

    Args:
        triangle: As in `compute_chain_ladder`.
        selected_factors: Length-(n_dev - 1) factor set used for the
            point estimate.
        excluded: Outlier exclusions to honour.
        outlier_threshold: Absolute residual threshold for flagging
            cells (default 2.0).

    Returns either:
        - On success: `{calendar_year, independence, inflation,
          outliers, overall}` — each test object carries `stat`,
          `p_value`, `verdict`, `summary`, `recommendation`. The
          `outliers` object also reports `count`, `severity`
          (clean / mild / moderate / severe), and a list of flagged
          cells.
        - On license failure: `{error: "pro_license_required",
          status: {...}}`.
    """
    blocked = require_pro_or_explain()
    if blocked is not None:
        return blocked
    return _with_disclaimer(methods_pro.interpret_diagnostics(
        triangle, selected_factors,
        excluded=_excluded_to_set(excluded),
        outlier_threshold=float(outlier_threshold),
    ))


@mcp.tool()
def sensitivity_analysis(
    triangle: list[list[float | None]],
    selected_factors: list[float] | None = None,
    tail: float = 1.0,
    excluded: list[list[int]] | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    """Drop each observable link ratio one at a time, rerun the chain
    ladder, and rank the link ratios by their impact on total IBNR.
    **Pro tier.**

    The fastest way to find the few observations that are actually
    driving the projection. Use after `mack_diagnostics` flags outliers
    — these are the cells to investigate first.

    Args:
        triangle: As in `compute_chain_ladder`.
        selected_factors: Override factor set; defaults to volume-
            weighted.
        tail: Multiplicative tail factor.
        excluded: Existing exclusions; the analysis honours these and
            tests one additional cell at a time.
        top_n: Cap on the number of "most influential" cells returned.
            Default 10. Set higher for larger triangles.

    Returns either:
        - On success: `{baseline_ibnr, n_tested, top_influential[],
          summary}` — each `top_influential` entry has `row`, `dev`,
          `ratio`, `ibnr_with_excluded`, `ibnr_delta`, `ibnr_delta_pct`.
        - On license failure: `{error, status}`.
    """
    blocked = require_pro_or_explain()
    if blocked is not None:
        return blocked
    return _with_disclaimer(methods_pro.sensitivity_analysis(
        triangle,
        selected_factors=selected_factors,
        tail=float(tail),
        excluded=_excluded_to_set(excluded),
        top_n=int(top_n),
    ))


@mcp.tool()
def tail_extrapolation(
    selected_factors: list[float],
    n_extra: int = 6,
) -> dict[str, Any]:
    """Fit parametric tail models to the late development factors and
    extrapolate forward. **Pro tier.**

    Fits two candidate models — exponential decay
    (`ln(f_j - 1) = a + b·j`) and inverse-power
    (`ln(f_j - 1) = a + b·ln(j+1)`) — picks the better R², and
    returns the implied tail factor for plugging back into
    `compute_chain_ladder(tail=…)`.

    Use this when the triangle obviously hasn't reached ultimate by
    the last observed development period — i.e., the last selected
    factor is still meaningfully above 1.

    Args:
        selected_factors: The factor set you want to extrapolate from.
        n_extra: How many extra development periods to project. Default
            6 (covers most P&C lines).

    Returns either:
        - On success: `{fits[], recommended, summary}` — each `fits`
          entry has `model`, `parameters`, `r_squared`,
          `extrapolated[]`, `tail_factor`.
        - On license failure: `{error, status}`.
    """
    blocked = require_pro_or_explain()
    if blocked is not None:
        return blocked
    return _with_disclaimer(methods_pro.tail_extrapolation(
        selected_factors=selected_factors,
        n_extra=int(n_extra),
    ))


@mcp.tool()
def compare_methods(
    triangle: list[list[float | None]],
    a_priori_ultimates: list[float],
    selected_factors: list[float] | None = None,
    tail: float = 1.0,
    excluded: list[list[int]] | None = None,
) -> dict[str, Any]:
    """Run chain ladder + Bornhuetter-Ferguson on the same triangle and
    return a side-by-side comparison. **Pro tier.**

    The canonical "second opinion" — when both methods agree, the
    reserve is defensible; when they diverge, the divergence is the
    finding. Reports total deltas plus the single AY where the two
    methods disagree most.

    Args:
        triangle: As in `compute_chain_ladder`.
        a_priori_ultimates: One expected ultimate per AY for the BF
            method.
        selected_factors, tail, excluded: As in `compute_chain_ladder`.

    Returns either:
        - On success: `{chain_ladder, bornhuetter_ferguson, diffs_by_ay,
          total_diff_ultimate, total_diff_ibnr, largest_divergence}`.
        - On license failure: `{error, status}`.
    """
    blocked = require_pro_or_explain()
    if blocked is not None:
        return blocked
    return _with_disclaimer(methods_pro.compare_methods(
        triangle, a_priori_ultimates,
        selected_factors=selected_factors,
        tail=float(tail),
        excluded=_excluded_to_set(excluded),
    ))


# ---------------------------------------------------------------------------
# Free-tier (continued)
# ---------------------------------------------------------------------------

@mcp.tool()
def sample_triangle() -> dict[str, Any]:
    """Return the classic textbook 10×10 cumulative-paid triangle
    (Friedland-style). Useful for demos, examples, and verifying the
    server is working — feed it to `compute_chain_ladder` to get the
    well-known parity values (Paid 49,458 / Ultimate 65,883 /
    IBNR 16,425 / Mack SE ±354.61).

    Returns:
        - `triangle`: the 10×10 list with the lower-right as null
        - `n_acc`: 10
        - `n_dev`: 10
        - `expected_totals`: well-known parity values for cross-checking
    """
    tri = cl.sample_triangle()
    return _with_disclaimer({
        "triangle": tri,
        "n_acc": 10,
        "n_dev": 10,
        "expected_totals": {
            "total_latest":   49458.0,
            "total_ultimate": 65883.37,
            "total_ibnr":     16425.37,
            "mack_se_total":  354.61,
        },
    })
