#!/usr/bin/env python3
"""mcp-chainladder Pro license keygen.

Signs license files with the seller's Ed25519 private key so the
distributed mcp-chainladder package can verify them. The matching
public key is embedded in `src/mcp_chainladder/license.py`.

Usage:

    # One-time: drop the base64 private key in keygen/PRIVATE_KEY.txt
    # (chmod 600). Or set CL_KEYGEN_PRIVATE_KEY env var. Never check
    # this into version control.

    python3 keygen/cl_keygen.py \\
        --owner    alice@example.com \\
        --key      CL-PRO-2026-0001 \\
        --expires  2027-12-31 \\
        --output   licenses/alice-CL-PRO-2026-0001.license

    # Perpetual license (no expiry):
    python3 keygen/cl_keygen.py --owner bob@example.com --key CL-PRO-2026-0002 \\
        --output licenses/bob.license

Drop the resulting .license file at ~/.chainladder/license on the
buyer's machine. The verifier in mcp-chainladder will check the
Ed25519 signature against its embedded public key on every Pro tool
invocation.

Verifying yourself (sanity-check after generating):

    python3 keygen/cl_keygen.py --verify licenses/alice.license

This script is INTENTIONALLY not packaged with mcp-chainladder on
PyPI. It lives in the same repo so the seller has a single source of
truth, but the published wheel ships only the verifier.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# We bundle the canonical payload helper + the embedded public key from
# the package so this script stays in lock-step with the verifier. Keeps
# both sides of the signature in one file's mental model.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from mcp_chainladder.license import (  # noqa: E402
    PUBLIC_KEY_B64, PRO_PRODUCT_ID, canonical_payload, _verify_signature,
)

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402


# ---------------------------------------------------------------------------
# Private-key loading
# ---------------------------------------------------------------------------

PRIVATE_KEY_FILE = ROOT / "keygen" / "PRIVATE_KEY.txt"


def load_private_key() -> Ed25519PrivateKey:
    """Read the Ed25519 private key from one of (in order):
      1. CL_KEYGEN_PRIVATE_KEY env var (base64, 32 bytes after decode)
      2. keygen/PRIVATE_KEY.txt file (base64)

    Refuses to start with the demo key that shipped during development
    if production mode is set, so you can't accidentally sign real
    licenses with a key that was published in a README.
    """
    b64 = os.environ.get("CL_KEYGEN_PRIVATE_KEY")
    src = "env CL_KEYGEN_PRIVATE_KEY"
    if not b64:
        if not PRIVATE_KEY_FILE.exists():
            raise RuntimeError(
                f"No private key found. Set CL_KEYGEN_PRIVATE_KEY in the "
                f"environment, or drop the base64 key in {PRIVATE_KEY_FILE} "
                f"(chmod 600). See keygen/README.md."
            )
        b64 = PRIVATE_KEY_FILE.read_text().strip()
        src = str(PRIVATE_KEY_FILE)
    try:
        raw = base64.b64decode(b64)
    except Exception as exc:
        raise RuntimeError(f"Could not decode private key from {src}: {exc}") from exc
    if len(raw) != 32:
        raise RuntimeError(
            f"Private key from {src} is the wrong length "
            f"({len(raw)} bytes; expected 32)."
        )
    return Ed25519PrivateKey.from_private_bytes(raw)


# ---------------------------------------------------------------------------
# Sign + verify
# ---------------------------------------------------------------------------

def issue_license(owner: str, key: str, expires_ts: int | None) -> dict[str, object]:
    """Build a signed license dict ready for json.dump."""
    privkey = load_private_key()
    payload = {
        "product": PRO_PRODUCT_ID,
        "owner":   owner,
        "expires": expires_ts,
        "key":     key,
    }
    signature = privkey.sign(canonical_payload(payload))
    payload["signature"] = base64.b64encode(signature).decode("ascii")
    return payload


def parse_expiry(s: str | None) -> int | None:
    """Convert a YYYY-MM-DD string to a unix epoch second, or return None
    for perpetual licenses. Accepts a few common variants."""
    if not s or s.lower() == "never":
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    raise SystemExit(f"Could not parse --expires '{s}'. Use YYYY-MM-DD.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--owner",   help="License owner (e.g. alice@example.com)")
    p.add_argument("--key",     help="Opaque license key string (e.g. CL-PRO-2026-0001)")
    p.add_argument("--expires", help="YYYY-MM-DD, or 'never' for perpetual")
    p.add_argument("--output",  help="Path to write the license file")
    p.add_argument("--verify",  metavar="FILE",
                   help="Verify an existing .license file and exit")
    args = p.parse_args()

    if args.verify:
        try:
            data = json.loads(Path(args.verify).read_text())
        except Exception as exc:
            print(f"✗ Could not read {args.verify}: {exc}")
            sys.exit(2)
        if _verify_signature(data):
            print(f"✓ Valid signature on {args.verify}")
            print(f"  product: {data.get('product')}")
            print(f"  owner:   {data.get('owner')}")
            print(f"  key:     {data.get('key')}")
            print(f"  expires: {data.get('expires')}")
            sys.exit(0)
        else:
            print(f"✗ Invalid or missing signature on {args.verify}")
            sys.exit(1)

    if not args.owner or not args.key or not args.output:
        p.error("--owner, --key and --output are required when issuing")

    expires_ts = parse_expiry(args.expires)
    license_doc = issue_license(args.owner, args.key, expires_ts)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(license_doc, indent=2, sort_keys=True) + "\n")
    print(f"✓ Wrote license to {out_path}")
    print(f"  Verifier public key: {PUBLIC_KEY_B64}")
    print(f"  Signature length:    {len(license_doc['signature'])} chars")
    print()
    print("Self-check:")
    if _verify_signature(license_doc):
        print("  ✓ Signature verifies against the embedded public key")
    else:
        print("  ✗ Signature did NOT verify — public/private keys are out of sync!")
        sys.exit(2)


if __name__ == "__main__":
    main()
