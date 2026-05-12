# Marketplace / directory submissions

Three places worth listing `mcp-chainladder`, in order of trust and
discovery value. Each section is copy-paste-ready — the descriptions
deliberately re-use the same language so your listings stay
consistent.

---

## 1. Anthropic — Connectors directory

This is the curated list you see at the 🔌 icon inside Claude Desktop /
claude.ai. Listing here is the strongest trust signal and the broadest
distribution; getting listed requires:

- A live PyPI package (do `PYPI_PUBLISH.md` first)
- A public GitHub / GitLab repo with README + LICENSE
- A working `claude_desktop_config.json` snippet

**Process** (as of this build): open an issue on
<https://github.com/modelcontextprotocol/servers> with the template
"Add server" — submission goes through PR review. They also maintain
the registry at <https://github.com/modelcontextprotocol/registry>
where you can submit yourself.

**Listing fields to fill in:**

| Field | Value |
|---|---|
| Name | Chain Ladder |
| Slug | `chainladder` (must be unique within the registry) |
| Description (short, ≤140 chars) | *Actuarial chain-ladder reserving for cumulative loss triangles — factors, IBNR, Mack stochastic stats, and assumption diagnostics.* |
| Long description | Use the README's "What it does" + tools table |
| Category | `finance` (or `data-analysis` — both apply) |
| Repository URL | `https://github.com/datalattice/mcp-chainladder` |
| Homepage | `https://chainladder.app` (if/when you have one) |
| License | MIT |
| Author | Data Analytics Actuary |
| Install command | `uvx mcp-chainladder` |
| Configuration example | (paste the JSON below) |
| Tools | List the 8 (or 9 once BF lands) tool names + one-line descriptions each |

**Configuration snippet to attach:**

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

**Likely review questions you'll need to answer:**

- *Does the server make any network requests?* → No. Pure-local
  calculation, no telemetry, no analytics.
- *Does it touch files outside the user's explicit input?* → Only
  reads CSVs at paths the user supplies; never writes.
- *Are there auth requirements or API keys?* → No, free tier is
  completely standalone. (Pro tier checks a local license file in
  `~/.chainladder/license`; mention this if asked.)
- *Sandbox compatibility?* → Pure-Python stdlib; no native deps.

---

## 2. mcp.so

Community-maintained registry at <https://mcp.so>. Listings are
self-service through a PR to <https://github.com/chatmcp/mcp-directory>.

**Submission YAML** to add under `data/servers/`:

```yaml
name: mcp-chainladder
display_name: Chain Ladder
description: |
  Actuarial chain-ladder reserving for cumulative loss triangles —
  factors, IBNR, Mack (1993) stochastic stats, and Mack (1994)
  assumption diagnostics. Pure-Python, no network access.
url: https://github.com/datalattice/mcp-chainladder
language: python
category:
  - finance
  - data-analysis
license: MIT
install: |
  uvx mcp-chainladder
config: |
  {
    "mcpServers": {
      "chainladder": {
        "command": "uvx",
        "args": ["mcp-chainladder"]
      }
    }
  }
tools:
  - compute_chain_ladder
  - project_triangle
  - mack_stochastic
  - mack_diagnostics
  - parse_csv_triangle
  - to_incremental
  - to_cumulative
  - sample_triangle
verified: false
```

Submit as a PR with a descriptive title like *"Add mcp-chainladder
(actuarial reserving)"*.

---

## 3. Smithery

<https://smithery.ai> — the most polished commercial-ish MCP registry.
Has a Pro tier with built-in license-key gating and basic analytics.
Useful when the Pro tier lands.

**Quick start:**

1. Sign in with GitHub at <https://smithery.ai/signin>
2. Click **Publish a Server**
3. Point at the repo + the `pyproject.toml`
4. Fill in the metadata form — same fields as Anthropic's directory

**Smithery-specific extras:**

- **Featured listing** ($) — paid placement on category pages. Worth
  it once the Pro tier exists and you have real revenue to amortise.
- **Hosted runtime** — Smithery will run the server on their infra so
  Claude clients can use it without installing locally. Useful for
  the SaaS-y path, less useful here (chain-ladder is a fast local
  calc, no benefit to hosting it).
- **License keys** — built-in feature; less work than rolling your
  own `license.py` if you want to use it.

---

## Description variants by length

Reusable copy. Pick the one that fits each form's character limit.

**8 words:** *Chain-ladder reserving and Mack diagnostics for Claude.*

**20 words:** *Actuarial chain-ladder reserving for cumulative loss
triangles — factors, IBNR, Mack stochastic stats, and assumption
diagnostics. No network.*

**40 words:** *Hands Claude eight tools for actuarial chain-ladder
reserving: compute the projection (factors → CDF → ultimates → IBNR),
run Mack (1993) standard errors, check Mack (1994) assumptions
(calendar-year, independence, inflation), parse a CSV triangle from
disk, and convert between cumulative/incremental form. Pure Python,
no network calls.*

**80 words:** Use the README's "What it does" section.

---

## Keyword bundle

Drop these into the keywords/tags fields wherever they ask:

```
actuarial, chain ladder, reserving, IBNR, Mack, loss triangle,
loss development, age-to-age factors, stochastic reserving,
insurance, casualty, accident year, claims, statistical inference,
MCP, model context protocol, Claude
```

---

## Pre-submission checklist

Before opening the Anthropic PR or any other submission:

- [ ] PyPI release is live and installable via `uvx mcp-chainladder`
- [ ] GitHub repo is public and the README renders correctly
- [ ] LICENSE file present
- [ ] At least one tagged release (git tag `v1.0.0` + push)
- [ ] `pytest` is green (9 tests passing as of v1.0.0)
- [ ] The `claude_desktop_config.json` snippet has been
      tested end-to-end on a real Claude Desktop install
- [ ] You have a public URL or contact email in the package metadata
      (PyPI surfaces this; if you'd rather not put your personal email
      there, register `support@chainladder.app` and forward)
