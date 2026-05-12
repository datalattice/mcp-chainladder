# mcp-chainladder

[![PyPI](https://img.shields.io/pypi/v/mcp-chainladder.svg)](https://pypi.org/project/mcp-chainladder/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-chainladder.svg)](https://pypi.org/project/mcp-chainladder/)
[![License](https://img.shields.io/pypi/l/mcp-chainladder.svg)](LICENSE)

**Actuarial chain-ladder reserving for Claude.** A
[Model Context Protocol](https://modelcontextprotocol.io) server that
hands Claude the tools to compute IBNR, project ultimates, run Mack
(1993) stochastic error estimates, check Mack (1994) model
assumptions, and parse loss triangles from CSV — all from a natural-
language conversation.

> **Calculation only — not actuarial advice.** This is a mechanical
> chain-ladder calculator. Selection of data, factors, tails, and
> exclusions, and the interpretation of stochastic error measures,
> require professional actuarial judgement.

---

## What it does

Eight tools, exposed over MCP. Claude picks the right one when you ask
a question; you don't have to call them by name.

| Tool | When Claude reaches for it |
|---|---|
| `compute_chain_ladder` | "What's the IBNR on this triangle?" — the workhorse |
| `project_triangle` | "What does the full projected triangle look like?" |
| `mack_stochastic` | "What's the uncertainty on the total reserve?" |
| `mack_diagnostics` | "Are there outliers or trend issues?" |
| `parse_csv_triangle` | "Run the chain ladder on this CSV file" |
| `to_incremental` | "Show me the incremental development pattern" |
| `to_cumulative` | "Cumulate these incremental values" |
| `sample_triangle` | "Show me a working example" — quick demo |

All numerical conventions match the [Mack 1993](https://www.casact.org/sites/default/files/database/astin_vol23no2_213.pdf)
and [Mack 1994](https://www.casact.org/sites/default/files/database/proceed_proceed94_94101.pdf) papers; results are stable to ~1e-12 against
hand calculation on the textbook 10×10 triangle.

---

## Install

```bash
pipx install mcp-chainladder
# or, to run on demand without installing:
uvx mcp-chainladder
```

Python 3.10 or newer; no other runtime dependencies beyond the official
MCP SDK.

## Hook into Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "chainladder": {
      "command": "uvx",
      "args": ["mcp-chainladder"]
    }
  }
}
```

Quit and reopen Claude Desktop. The triangle tools appear under the 🔌
icon in any conversation.

For Cursor / Cline / Continue / Zed — same `mcpServers` block, each app
has its own config file location (their docs walk you through it).

---

## Examples

### Run the chain ladder on a CSV

```
Me: I have a paid-loss triangle at ~/Desktop/motor_2026Q1.csv.
    Run the chain ladder and tell me the IBNR.

Claude: [calls parse_csv_triangle, then compute_chain_ladder]
        Loaded a 10×10 cumulative triangle. Using volume-weighted
        factors:
          • Total paid to date: 49,458,000 USD
          • Total ultimate:     65,883,400 USD
          • Total IBNR:         16,425,400 USD
        Selected factors trend from 1.879 at the front of the
        triangle down to 1.002 at the tail.
```

### Check whether you should worry about assumptions

```
Me: Same triangle — any reason not to trust the projection?

Claude: [calls mack_diagnostics]
        Three flags worth a look:
        • Inflation trend: slope 0.053, p ≈ 1e-12 — STRONG evidence
          link ratios are drifting upward across accident years.
          This violates Mack's homogeneity assumption; consider
          weighting recent years more.
        • Calendar-year: Z = 0.0, p = 1.0 — no diagonal effect.
        • Independence: Z = -0.35, p = 0.73 — no obvious dependence
          across development columns.
        • Outliers: 0 cells exceed |2σ|.

        The inflation finding is the one to act on.
```

### Exclude an outlier and re-run

```
Me: Drop the link ratio at AY 3, dev period 2→3. What changes?

Claude: [calls compute_chain_ladder with excluded=[[2, 1]]]
        Excluding (AY 3, 2→3):
          • Volume factor at 2→3 moves from 1.331 to 1.328
          • Total IBNR moves from 16,425 to 16,389 (−36)
          • Mack SE total moves from ±354.6 to ±348.2
        Net: small enough to be a "robustness check passes" rather
        than a finding.
```

---

## Tool reference

Each tool returns a JSON object (or a 2-D list, in the case of
`project_triangle`/`to_incremental`/`to_cumulative`). Claude reads the
descriptions and types directly from the server — you don't need to
memorise the shapes — but here's the cheat sheet.

### `compute_chain_ladder(triangle, selected_factors?, tail?, excluded?)`

End-to-end chain ladder.

| Field returned | Meaning |
|---|---|
| `volume_factors[j]` | All-year volume-weighted age-to-age factor for transition j→j+1 |
| `simple_factors[j]` | Unweighted average of individual link ratios |
| `selected_factors[j]` | The factor set actually used to project (defaults to volume) |
| `individual_factors[i][j]` | Per-row link ratio `C[i,j+1] / C[i,j]`; null where the pair is unobserved |
| `cdf[j]` | Cumulative dev factor to ultimate; `cdf[-1] == tail` |
| `latest_diagonal[i]` | Most recent observed value per AY |
| `ultimates[i]` | Projected ultimate per AY |
| `ibnr[i]` | Ultimate − Latest per AY |
| `total_*` | Sums of the three above |
| `n_acc`, `n_dev` | Triangle dimensions |

### `mack_stochastic(triangle, selected_factors, excluded?)`

Mack (1993) distribution-free standard errors. Returns σ̂²_j per dev
period (tail-rule backfilled when only one observation), SE & CV per
row, and SE_total / CV_total including cross-row covariance per eq.
5.15.

### `mack_diagnostics(triangle, selected_factors, excluded?, outlier_threshold?)`

Returns standardised residuals, outliers (`|r| > threshold`, default
2.0), the calendar-year sign test, Spearman independence test across
adjacent dev columns, and the inflation slope of mean log-link-ratio
against accident-year index.

p-value bands to translate to plain English:

```
p < 0.005 → strong evidence
p < 0.05  → significant
p < 0.10  → borderline
p ≥ 0.10  → no evidence
```

### `parse_csv_triangle(path)`

Reads a CSV from disk, treats blank / NA / NaN / N/A / − cells as
unobserved, strips embedded thousand-separator commas, and skips
header / metadata rows. Returns the triangle + dimensions + the
absolute path read (useful for the assistant to confirm what it
loaded).

### `project_triangle(triangle, selected_factors)`

Fills the lower-right of the triangle with chain-ladder projections.
Returns a fully-rectangular `list[list[float]]` (no nulls). NaN where
a row has no observation to project forward from.

### `to_incremental(cumulative)` / `to_cumulative(incremental)`

Two conversions. Unobserved cells stay unobserved; the inverse on
observed cells is exact.

### `sample_triangle()`

Returns the textbook 10×10 cumulative paid triangle. Use as a
self-check: pass it to `compute_chain_ladder` and you should get
**Paid 49,458 / Ultimate 65,883 / IBNR 16,425**.

---

## Triangle format

```python
[
    # AY 1 — fully developed
    [1000, 1855, 2423, 2988, 3335, 3483, 3552, 3603, 3624, 3631],
    # AY 2 — observed through dev 9
    [1113, 2103, 2774, 3422, 3844, 4010, 4090, 4148, 4172, None],
    # …
    # AY 10 — only the first observation
    [2640, None, None, None, None, None, None, None, None, None]
]
```

- Outer index = accident year, oldest first
- Inner index = development period, 0 = first age
- Use `None` (or JSON `null`) for unobserved cells
- All rows must be the same length — pad with trailing `null`

---

## Testing

```bash
pipx install --editable mcp-chainladder
pytest -q
```

Tests pin every public tool against the textbook triangle's well-known
parity values to ~1e-9.

## Pro tier

The free tier covers all 8 tools listed above. **Pro** unlocks
additional methods + bulk workflows, gated by a local license file
at `~/.chainladder/license` (or wherever `$CHAINLADDER_LICENSE_FILE`
points). Get a license at <https://chainladder.app/pro>.

| Pro tool | What it does |
|---|---|
| `pro_license_status` | Inspect current license state (free to call) |
| `interpret_diagnostics` | Mack tests with verdict labels + plain-English summaries + recommended actions |
| `sensitivity_analysis` | Drop each link ratio one-at-a-time and rank by IBNR impact |
| `tail_extrapolation` | Fit exponential + inverse-power tail models, recommend best fit |
| `bornhuetter_ferguson` | BF reserving method with side-by-side CL comparison |
| `compare_methods` | Run CL + BF in one call, report deltas + largest divergence |
| `generate_pdf_report` *(coming v1.2)* | Full 5-page actuarial PDF — cover / triangle / factors / results / 3D loss surface |
| `batch_csv_processing` *(coming v1.2)* | Fold the chain ladder over a directory of CSV triangles |
| `cape_cod`, `mack_bf` *(coming v1.3)* | Additional reserving methods, all returning side-by-side comparisons |

### License file format

```json
{
  "product":  "mcp-chainladder-pro",
  "owner":    "alice@example.com",
  "expires":  null,
  "key":      "CL-PRO-1A2B3C4D",
  "signature": "…"
}
```

Drop it at `~/.chainladder/license` (the file's directory must exist;
the server doesn't create it). Pro tools immediately respond as
unlocked the next time Claude calls them.

When the license is missing or expired, every Pro tool returns
`{"error": "pro_license_required", "status": {...}}` instead of
computing — Claude reads the status and points you to the upgrade
URL. The free-tier tools always work regardless of license state.

## License

MIT. See [`LICENSE`](LICENSE).

Built on top of the open-source [Chain Ladder for
macOS](https://github.com/datalattice/chainladder) app, which
exposes the same math through a native UI.
