"""Pro-tier tests — license gating, BF math, the unlocked vs gated paths."""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import pytest

from mcp_chainladder import chainladder as cl
from mcp_chainladder.license import PRO_PRODUCT_ID, LicenseStatus, check_pro_license
from mcp_chainladder.server import (
    bornhuetter_ferguson,
    compare_methods,
    interpret_diagnostics,
    pro_license_status,
    sensitivity_analysis,
    tail_extrapolation,
)


@pytest.fixture
def textbook() -> list[list[float | None]]:
    return cl.sample_triangle()


@pytest.fixture
def fresh_license(tmp_path: Path) -> Path:
    """Write a valid, never-expiring license file and point the env var
    at it. Tests run in DEV_MODE so the unsigned stub still verifies —
    the signature path itself is exercised by the keygen smoke test
    below. Yields the file path so individual tests can mutate it."""
    licfile = tmp_path / "license"
    licfile.write_text(json.dumps({
        "product":   PRO_PRODUCT_ID,
        "owner":     "test@example.com",
        "expires":   None,
        "key":       "CL-PRO-TEST-0001",
        "signature": "test-stub",
    }))
    os.environ["CHAINLADDER_LICENSE_FILE"]      = str(licfile)
    os.environ["CHAINLADDER_LICENSE_DEV_MODE"]  = "1"
    yield licfile
    os.environ.pop("CHAINLADDER_LICENSE_FILE", None)
    os.environ.pop("CHAINLADDER_LICENSE_DEV_MODE", None)


@pytest.fixture
def no_license() -> None:
    """Force the license loader to look at a non-existent path."""
    os.environ["CHAINLADDER_LICENSE_FILE"]     = "/tmp/nonexistent-license-path-xyz"
    os.environ["CHAINLADDER_LICENSE_DEV_MODE"] = "1"
    yield
    os.environ.pop("CHAINLADDER_LICENSE_FILE", None)
    os.environ.pop("CHAINLADDER_LICENSE_DEV_MODE", None)


# ---------------------------------------------------------------------------
# License plumbing
# ---------------------------------------------------------------------------

def test_license_status_when_missing(no_license: None) -> None:
    s = pro_license_status()
    assert s["active"] is False
    assert s["owner"] is None
    assert "Pro license" in s["message"]
    assert s["upgrade_url"].startswith("https://")


def test_license_status_when_valid(fresh_license: Path) -> None:
    s = pro_license_status()
    assert s["active"] is True
    assert s["owner"] == "test@example.com"
    assert s["expires"] is None


def test_license_status_expired(fresh_license: Path) -> None:
    fresh_license.write_text(json.dumps({
        "product": PRO_PRODUCT_ID,
        "owner":   "test@example.com",
        "expires": int(time.time()) - 86400,    # yesterday
        "key":     "CL-PRO-TEST-0001",
    }))
    s = pro_license_status()
    assert s["active"] is False
    assert "expired" in s["message"].lower()


def test_license_status_wrong_product(fresh_license: Path) -> None:
    fresh_license.write_text(json.dumps({
        "product": "some-other-product",
        "owner":   "test@example.com",
    }))
    s = pro_license_status()
    assert s["active"] is False
    assert "different product" in s["message"].lower()


# ---------------------------------------------------------------------------
# Bornhuetter-Ferguson — math + gating
# ---------------------------------------------------------------------------

def test_bf_blocks_without_license(
    no_license: None, textbook: list[list[float | None]],
) -> None:
    """Without a license the tool must NOT compute anything and instead
    return an error envelope with an upgrade URL."""
    a_priori = [10000.0] * 10
    result = bornhuetter_ferguson(textbook, a_priori)
    assert result.get("error") == "pro_license_required"
    assert "status" in result
    assert result["status"]["active"] is False
    assert result["status"]["upgrade_url"].startswith("https://")
    # Crucially, no BF math fields should leak through:
    assert "bf_ultimates" not in result


def test_bf_runs_with_license(
    fresh_license: Path, textbook: list[list[float | None]],
) -> None:
    """BF projection on the textbook triangle, with a flat 10,000 a-priori
    ultimate per AY. Verifies the math + the side-by-side CL comparison."""
    a_priori = [10000.0] * 10
    result = bornhuetter_ferguson(textbook, a_priori)
    assert "error" not in result
    assert len(result["bf_ultimates"]) == 10
    assert len(result["bf_ibnr"]) == 10
    # CL ultimates should match the textbook parity values exactly.
    expected_cl = [
        3631.0, 4180.058498896247, 4855.332195546655,  5629.506975307957,
        6514.219391389273, 6935.669423630087, 7355.179718982286,
        8190.475923909978, 8849.470026048471, 9742.457640557217,
    ]
    for got, want in zip(result["cl_ultimates"], expected_cl):
        assert math.isclose(got, want, abs_tol=1e-9)
    # BF identity: bf_ultimate[i] == latest[i] + (1 - used_up[i]) * a_priori[i].
    latest = [3631, 4172, 4818, 5508, 6249, 6362, 6020, 5552, 4506, 2640]
    for i in range(10):
        expected = latest[i] + (1 - result["used_up_proportion"][i]) * a_priori[i]
        assert math.isclose(result["bf_ultimates"][i], expected, abs_tol=1e-9)


def test_bf_length_mismatch(
    fresh_license: Path, textbook: list[list[float | None]],
) -> None:
    """BF must reject an a-priori vector of the wrong length so the user
    sees a clear error instead of silently broken numbers."""
    with pytest.raises(ValueError):
        bornhuetter_ferguson(textbook, [10000.0] * 9)   # n=10 triangle


# ---------------------------------------------------------------------------
# interpret_diagnostics
# ---------------------------------------------------------------------------

def test_interpret_diagnostics_blocks_without_license(
    no_license: None, textbook: list[list[float | None]],
) -> None:
    r = interpret_diagnostics(textbook, [1.0] * 9)
    assert r.get("error") == "pro_license_required"


def test_interpret_diagnostics_textbook(
    fresh_license: Path, textbook: list[list[float | None]],
) -> None:
    """Run on the textbook triangle. Calendar-year + independence should
    be 'no evidence', inflation should be 'strong evidence' (β ≈ 0.053,
    p ≈ 1e-12), and outliers should be 'clean'."""
    sel = [
        1.8790508118056926, 1.3312707641196013, 1.2074325598943596,
        1.120732786822153,  1.0457860971965902, 1.0199418836533531,
        1.0142015653998224, 1.0058057024900013, 1.0019315673289184,
    ]
    r = interpret_diagnostics(textbook, sel)
    assert r["calendar_year"]["verdict"] == "no evidence"
    assert r["independence"]["verdict"]  == "no evidence"
    assert r["inflation"]["verdict"]     == "strong evidence"
    assert r["outliers"]["count"]        == 0
    assert r["outliers"]["severity"]     == "clean"
    # Each test has a non-empty summary + recommendation.
    for key in ("calendar_year", "independence", "inflation"):
        assert len(r[key]["summary"]) > 20
        assert len(r[key]["recommendation"]) > 10
    assert "Caution" in r["overall"] or "strong" in r["overall"].lower()


# ---------------------------------------------------------------------------
# sensitivity_analysis
# ---------------------------------------------------------------------------

def test_sensitivity_analysis_runs_with_license(
    fresh_license: Path, textbook: list[list[float | None]],
) -> None:
    r = sensitivity_analysis(textbook, top_n=5)
    assert "error" not in r
    assert math.isclose(r["baseline_ibnr"], 16425.369794268172, abs_tol=1e-9)
    assert r["n_tested"] > 0
    assert len(r["top_influential"]) == 5
    # Top entry should have a non-zero IBNR delta.
    assert abs(r["top_influential"][0]["ibnr_delta"]) > 0


def test_sensitivity_analysis_blocked(
    no_license: None, textbook: list[list[float | None]],
) -> None:
    r = sensitivity_analysis(textbook)
    assert r.get("error") == "pro_license_required"


# ---------------------------------------------------------------------------
# tail_extrapolation
# ---------------------------------------------------------------------------

def test_tail_extrapolation_textbook(fresh_license: Path) -> None:
    sel = [
        1.8790508118056926, 1.3312707641196013, 1.2074325598943596,
        1.120732786822153,  1.0457860971965902, 1.0199418836533531,
        1.0142015653998224, 1.0058057024900013, 1.0019315673289184,
    ]
    r = tail_extrapolation(sel, n_extra=4)
    assert "error" not in r
    assert len(r["fits"]) == 2
    for f in r["fits"]:
        assert f["model"] in ("exponential", "inverse_power")
        assert 0 <= f["r_squared"] <= 1
        assert len(f["extrapolated"]) == 4
        # Tail factor = product of extrapolated factors, all close to 1.
        assert f["tail_factor"] > 0
    assert r["recommended"] in ("exponential", "inverse_power")


def test_tail_extrapolation_blocked(no_license: None) -> None:
    r = tail_extrapolation([1.5, 1.2, 1.1, 1.05, 1.02])
    assert r.get("error") == "pro_license_required"


# ---------------------------------------------------------------------------
# compare_methods
# ---------------------------------------------------------------------------

def test_compare_methods_textbook(
    fresh_license: Path, textbook: list[list[float | None]],
) -> None:
    a_priori = [10000.0] * 10
    r = compare_methods(textbook, a_priori)
    assert "error" not in r
    assert "chain_ladder" in r and "bornhuetter_ferguson" in r
    # CL totals match parity to 1e-9.
    assert math.isclose(r["chain_ladder"]["total_ultimate"],
                        65883.36979426818, abs_tol=1e-9)
    # Diffs by AY must match the explicit subtraction.
    cl_u = r["chain_ladder"]["ultimates"]
    bf_u = r["bornhuetter_ferguson"]["ultimates"]
    diffs = r["diffs_by_ay"]
    for i in range(10):
        assert math.isclose(diffs[i], bf_u[i] - cl_u[i], abs_tol=1e-9)
    assert r["largest_divergence"]["ay"] in range(1, 11)


def test_compare_methods_blocked(
    no_license: None, textbook: list[list[float | None]],
) -> None:
    r = compare_methods(textbook, [10000.0] * 10)
    assert r.get("error") == "pro_license_required"


# ---------------------------------------------------------------------------
# Disclaimer is attached to every Pro tool too
# ---------------------------------------------------------------------------

def test_real_signature_round_trip(tmp_path: Path) -> None:
    """Issue a license with the seller's real private key (loaded from
    keygen/PRIVATE_KEY.txt, which is gitignored), and verify the
    embedded public key accepts it — non-dev-mode. This is the only
    test that exercises the actual signature path; without it the
    rest of the suite passes purely on the dev-mode bypass and
    signature drift could go undetected.

    Skipped automatically if PRIVATE_KEY.txt isn't present, so
    contributors who clone the repo without the production key still
    see a green suite.
    """
    private_key_file = Path(__file__).resolve().parent.parent \
        / "keygen" / "PRIVATE_KEY.txt"
    if not private_key_file.exists():
        pytest.skip("No keygen/PRIVATE_KEY.txt — skipping signed-license test.")

    # Use the keygen library directly to issue.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "keygen"))
    import cl_keygen

    license_doc = cl_keygen.issue_license(
        owner="signed@example.com",
        key="CL-PRO-SIGNED-TEST-0001",
        expires_ts=None,
    )
    licfile = tmp_path / "signed.license"
    licfile.write_text(json.dumps(license_doc))

    # Point the verifier at the real signed file with DEV_MODE OFF.
    os.environ["CHAINLADDER_LICENSE_FILE"] = str(licfile)
    os.environ.pop("CHAINLADDER_LICENSE_DEV_MODE", None)
    try:
        status = pro_license_status()
        assert status["active"] is True
        assert status["owner"]  == "signed@example.com"
    finally:
        os.environ.pop("CHAINLADDER_LICENSE_FILE", None)


def test_tampered_signature_rejected(tmp_path: Path) -> None:
    """A license with the wrong signature must NOT unlock Pro tools when
    dev-mode is off. Catches the "user edited their license file to
    change the expiry" attack."""
    private_key_file = Path(__file__).resolve().parent.parent \
        / "keygen" / "PRIVATE_KEY.txt"
    if not private_key_file.exists():
        pytest.skip("No keygen/PRIVATE_KEY.txt — skipping tampered-signature test.")

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "keygen"))
    import cl_keygen

    license_doc = cl_keygen.issue_license(
        owner="signed@example.com",
        key="CL-PRO-TAMPER-0001",
        expires_ts=None,
    )
    # Tamper: change the owner field after signing. The signature was
    # computed over a different canonical payload, so it shouldn't
    # verify anymore.
    license_doc["owner"] = "attacker@example.com"
    licfile = tmp_path / "tampered.license"
    licfile.write_text(json.dumps(license_doc))

    os.environ["CHAINLADDER_LICENSE_FILE"] = str(licfile)
    os.environ.pop("CHAINLADDER_LICENSE_DEV_MODE", None)
    try:
        status = pro_license_status()
        assert status["active"] is False
        assert "signature" in status["message"].lower()
    finally:
        os.environ.pop("CHAINLADDER_LICENSE_FILE", None)


def test_pro_tools_carry_disclaimer(
    fresh_license: Path, textbook: list[list[float | None]],
) -> None:
    sel = [1.879, 1.331, 1.207, 1.121, 1.046, 1.020, 1.014, 1.006, 1.002]
    a_priori = [10000.0] * 10
    for tool, args in [
        (bornhuetter_ferguson,    (textbook, a_priori)),
        (interpret_diagnostics,   (textbook, sel)),
        (sensitivity_analysis,    (textbook,)),
        (tail_extrapolation,      (sel,)),
        (compare_methods,         (textbook, a_priori)),
    ]:
        out = tool(*args)
        assert "disclaimer" in out, f"{tool.__name__} forgot the disclaimer"
        assert "actuarial advice" in out["disclaimer"].lower()
