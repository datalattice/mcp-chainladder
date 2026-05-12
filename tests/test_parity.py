"""Parity tests for the MCP server's tool functions.

Every test here pins the output of a tool call against the well-known
textbook-triangle values (matching the Swift port's 17 parity tests and
the original Python `test_chainladder.py`). If anything here breaks,
something downstream (factor table in the UI, IBNR in the PDF, the
Mack KPI) will silently be wrong.

We call the *server-side* wrappers (not the underlying `chainladder.py`
functions) so the wire format is exercised too — that's the contract
Claude actually sees.
"""
from __future__ import annotations

import math

import pytest

from mcp_chainladder import chainladder as cl
from mcp_chainladder.server import (
    compute_chain_ladder,
    mack_stochastic,
    mack_diagnostics,
    project_triangle,
    to_incremental,
    to_cumulative,
    sample_triangle,
)

TOL = 1e-9


# ---------------------------------------------------------------------------
# compute_chain_ladder
# ---------------------------------------------------------------------------

@pytest.fixture
def textbook() -> list[list[float | None]]:
    """Friedland-style cumulative paid triangle, 10×10."""
    return cl.sample_triangle()


def _close(a: list[float], b: list[float]) -> None:
    """Assert two equal-length float lists are pointwise close to `TOL`."""
    assert len(a) == len(b), f"length mismatch: {len(a)} vs {len(b)}"
    for i, (x, y) in enumerate(zip(a, b)):
        assert math.isclose(x, y, abs_tol=TOL), \
            f"[{i}] {x!r} ≠ {y!r}"


def test_compute_chain_ladder_textbook(textbook: list[list[float | None]]) -> None:
    """End-to-end parity against the Swift port's 17 reference values."""
    r = compute_chain_ladder(textbook)

    _close(r["volume_factors"], [
        1.8790508118056926, 1.3312707641196013, 1.2074325598943596,
        1.120732786822153,  1.0457860971965902, 1.0199418836533531,
        1.0142015653998224, 1.0058057024900013, 1.0019315673289184,
    ])

    _close(r["simple_factors"], [
        1.882632454729669,  1.329471195734987,  1.2116292412168634,
        1.1205501493489398, 1.0454941675055265, 1.0199315708411638,
        1.0142137771524347, 1.0058071985977612, 1.0019315673289184,
    ])

    _close(r["cdf"], [
        3.690324863847431, 1.9639303209162164, 1.475229813384362,
        1.2217906509937353, 1.0901712391748015, 1.0424418933252158,
        1.022060089925192,  1.0077484839241708, 1.0019315673289184,
        1.0,
    ])

    _close(r["latest_diagonal"],
           [3631, 4172, 4818, 5508, 6249, 6362, 6020, 5552, 4506, 2640])

    _close(r["ultimates"], [
        3631.0, 4180.058498896247, 4855.332195546655,  5629.506975307957,
        6514.219391389273, 6935.669423630087, 7355.179718982286,
        8190.475923909978, 8849.470026048471, 9742.457640557217,
    ])

    _close(r["ibnr"], [
        0.0, 8.058498896247329, 37.332195546655385, 121.50697530795696,
        265.21939138927337, 573.6694236300873, 1335.1797189822864,
        2638.4759239099776, 4343.4700260484715, 7102.457640557217,
    ])

    assert math.isclose(r["total_latest"],   49458.0,            abs_tol=TOL)
    assert math.isclose(r["total_ultimate"], 65883.36979426818,  abs_tol=TOL)
    assert math.isclose(r["total_ibnr"],     16425.369794268172, abs_tol=TOL)
    assert r["n_acc"] == 10
    assert r["n_dev"] == 10


def test_compute_chain_ladder_exclusion_changes_factor(
    textbook: list[list[float | None]],
) -> None:
    """Excluding (0, 0) should move the volume factor at dev 0→1 ever so
    slightly. Confirms the `excluded` wire format is honoured."""
    baseline = compute_chain_ladder(textbook)["volume_factors"][0]
    excluded = compute_chain_ladder(textbook, excluded=[[0, 0]])["volume_factors"][0]
    assert math.isclose(excluded, 1.880742981777246, abs_tol=TOL)
    assert not math.isclose(baseline, excluded, abs_tol=1e-6), \
        "Excluding a row should move the factor; got identical values."


def test_compute_chain_ladder_custom_factors_used(
    textbook: list[list[float | None]],
) -> None:
    """Passing `selected_factors` makes them propagate through to CDF and
    therefore to the projected ultimates."""
    sel = [1.5] * 9
    r = compute_chain_ladder(textbook, selected_factors=sel)
    assert r["selected_factors"] == sel
    assert math.isclose(r["cdf"][-1], 1.0, abs_tol=TOL)
    assert math.isclose(r["cdf"][0], 1.5 ** 9, abs_tol=TOL)


# ---------------------------------------------------------------------------
# mack_stochastic
# ---------------------------------------------------------------------------

def test_mack_stochastic_totals(textbook: list[list[float | None]]) -> None:
    """Pin the total SE / CV against the Swift port's parity values."""
    base = compute_chain_ladder(textbook)
    m = mack_stochastic(textbook, base["selected_factors"])
    assert math.isclose(m["se_total"], 354.61334425880256,   abs_tol=TOL)
    assert math.isclose(m["cv_total"], 0.00538244090073325,  abs_tol=TOL)


def test_mack_stochastic_per_row(textbook: list[list[float | None]]) -> None:
    base = compute_chain_ladder(textbook)
    m = mack_stochastic(textbook, base["selected_factors"])
    _close(m["se_per_row"], [
        0.0, 0.040173855050462746, 0.17153253761424275, 0.764266057329312,
        0.9742503684553175, 12.696754074314455, 18.183723269542632,
        142.49749172023098, 166.42954487235298, 222.14385955023926,
    ])


# ---------------------------------------------------------------------------
# mack_diagnostics
# ---------------------------------------------------------------------------

def test_mack_diagnostics_textbook(textbook: list[list[float | None]]) -> None:
    base = compute_chain_ladder(textbook)
    d = mack_diagnostics(textbook, base["selected_factors"])
    assert math.isclose(d["calendar_year"]["z"],            0.0,                 abs_tol=TOL)
    assert math.isclose(d["calendar_year"]["p_two_sided"],  1.0,                 abs_tol=TOL)
    assert math.isclose(d["independence"]["z"],            -0.350992306507344,   abs_tol=TOL)
    assert math.isclose(d["independence"]["p_two_sided"],   0.7255941202009069,  abs_tol=TOL)
    assert math.isclose(d["inflation"]["slope"],            0.05326539396454834, abs_tol=TOL)
    # p ≈ 1.27e-12 — use a generous absolute tolerance.
    assert math.isclose(d["inflation"]["p_value"],          1.2734769653815747e-12, abs_tol=1e-18)
    # No |residual| > 2 cells on the textbook triangle.
    assert d["outliers"] == []


# ---------------------------------------------------------------------------
# conversion + ancillary tools
# ---------------------------------------------------------------------------

def test_project_triangle_fills_lower_right(textbook: list[list[float | None]]) -> None:
    base = compute_chain_ladder(textbook)
    out = project_triangle(textbook, base["selected_factors"])
    proj = out["triangle"]
    assert all(math.isfinite(v) for v in proj[0])  # row already complete
    # The very last AY had only the first observation; check the
    # ultimate equals latest × CDF[0].
    last = proj[-1]
    expected_ult = textbook[-1][0] * base["cdf"][0]
    assert math.isclose(last[-1], expected_ult, abs_tol=1e-8)
    assert "disclaimer" in out


def test_incremental_cumulative_roundtrip(textbook: list[list[float | None]]) -> None:
    inc = to_incremental(textbook)["triangle"]
    cum = to_cumulative(inc)["triangle"]
    for row_in, row_out in zip(textbook, cum):
        for a, b in zip(row_in, row_out):
            if a is None or b is None:
                assert a is None and b is None
            else:
                assert math.isclose(a, b, abs_tol=TOL)


def test_sample_triangle_returns_textbook() -> None:
    """The `sample_triangle` tool should return the same 10×10 fixture
    every other test uses, plus the published parity totals."""
    s = sample_triangle()
    assert s["n_acc"] == 10 and s["n_dev"] == 10
    assert math.isclose(s["expected_totals"]["total_latest"],   49458.0,    abs_tol=0.5)
    assert math.isclose(s["expected_totals"]["total_ultimate"], 65883.37,   abs_tol=0.5)
    assert math.isclose(s["expected_totals"]["total_ibnr"],     16425.37,   abs_tol=0.5)
    # The triangle returned should equal the underlying fixture.
    assert s["triangle"] == cl.sample_triangle()


def test_every_tool_returns_a_disclaimer(textbook: list[list[float | None]]) -> None:
    """Every free-tier tool must tag its response with the actuarial-use
    disclaimer so Claude has it in context when relaying numbers."""
    base = compute_chain_ladder(textbook)
    assert "disclaimer" in base
    assert "actuarial advice" in base["disclaimer"].lower()
    # Same for every other free-tier tool we touch in this file.
    for tool, args in [
        (sample_triangle,    ()),
        (project_triangle,   (textbook, base["selected_factors"])),
        (to_incremental,     (textbook,)),
        (to_cumulative,      (textbook,)),
    ]:
        out = tool(*args)
        assert "disclaimer" in out, f"{tool.__name__} forgot the disclaimer"
