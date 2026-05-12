"""Pro-tier license check with Ed25519 signature verification.

Looks for a license file at:

    $CHAINLADDER_LICENSE_FILE        (env override; useful for tests)
    ~/.chainladder/license           (the canonical user-installed path)

The file is JSON with the following shape:

    {
        "product":   "mcp-chainladder-pro",
        "owner":     "alice@example.com",
        "expires":   null | 1893456000,
        "key":       "CL-PRO-…",
        "signature": "base64(ed25519(canonical(payload)))"
    }

Verification uses an Ed25519 public key embedded below; the matching
private key lives only on the seller's machine (see `keygen/` in the
repo). The signature is computed over the canonical JSON of the
{product, owner, expires, key} fields — same algorithm both sides
must use so any byte drift fails verification.

If someone leaks their license file, an attacker can copy it onto
another machine, but they cannot mint new licenses without the
seller's private key. That's the practical bar a software-only
licensing scheme can hit; harder bars require hardware-backed
attestation, which doesn't fit the audience for this tool.

A `LicenseStatus` is what every Pro-gated tool returns inside its
"error" envelope when the user doesn't have a valid license — gives
Claude enough context to point the user to the upgrade page without
the tool itself having to know the URL.

For local development and CI tests, set
`CHAINLADDER_LICENSE_DEV_MODE=1` in the environment and the verifier
will accept unsigned license files. **Never** ship a build with that
env var baked in.
"""
from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


# ---------------------------------------------------------------------------
# Public verification key
# ---------------------------------------------------------------------------
# Base64 of the 32-byte Ed25519 public key. The matching private key is
# kept by the seller (see keygen/PRIVATE_KEY_DO_NOT_COMMIT.txt for the
# demo keypair we generated; rotate this in production).
PUBLIC_KEY_B64 = "rk7KGHx+Glf509cV6TlewclHZcbMoI71nSTowJ9ccPE="

PRO_PRODUCT_ID = "mcp-chainladder-pro"
UPGRADE_URL    = "https://chainladder.app/pro"
LICENSE_PATH   = Path.home() / ".chainladder" / "license"


@dataclass
class LicenseStatus:
    active:  bool
    owner:   str | None
    expires: int | None
    message: str
    upgrade_url: str = UPGRADE_URL

    def to_dict(self) -> dict[str, object]:
        return {
            "active":      self.active,
            "owner":       self.owner,
            "expires":     self.expires,
            "message":     self.message,
            "upgrade_url": self.upgrade_url,
        }


# ---------------------------------------------------------------------------
# Signature plumbing
# ---------------------------------------------------------------------------

def canonical_payload(data: dict[str, object]) -> bytes:
    """Build the byte-string the signature is computed over. JSON with
    sorted keys, no whitespace, no signature field. Both sides MUST
    produce the same canonical form for the signature to verify, so
    this function is the single source of truth on both the keygen
    and verifier sides."""
    signable = {
        "product": data.get("product"),
        "owner":   data.get("owner"),
        "expires": data.get("expires"),
        "key":     data.get("key"),
    }
    return json.dumps(signable, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verify_signature(data: dict[str, object]) -> bool:
    """Returns True iff the file's `signature` field is a valid Ed25519
    signature of `canonical_payload(data)` under the embedded public key."""
    sig_b64 = data.get("signature")
    if not isinstance(sig_b64, str) or not sig_b64:
        return False
    try:
        signature = base64.b64decode(sig_b64)
    except Exception:
        return False
    pubkey = Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64))
    try:
        pubkey.verify(signature, canonical_payload(data))
        return True
    except InvalidSignature:
        return False


# ---------------------------------------------------------------------------
# License loader
# ---------------------------------------------------------------------------

def check_pro_license() -> LicenseStatus:
    """Read the license file (if any) and decide whether Pro features
    should be unlocked. Always returns a status — never raises — so
    every Pro tool can call it once at the top of its body and react
    to the boolean.
    """
    path = Path(os.environ.get("CHAINLADDER_LICENSE_FILE", str(LICENSE_PATH)))
    if not path.exists():
        return LicenseStatus(
            active=False, owner=None, expires=None,
            message=(
                f"No Pro license found at {path}. "
                "Pro tools are gated until a signed license is installed. "
                f"Buy one at {UPGRADE_URL}."
            ),
        )
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        return LicenseStatus(
            active=False, owner=None, expires=None,
            message=f"License file at {path} is unreadable: {exc}",
        )

    if data.get("product") != PRO_PRODUCT_ID:
        return LicenseStatus(
            active=False, owner=None, expires=None,
            message=(
                f"License file at {path} is for a different product "
                f"({data.get('product')!r} vs {PRO_PRODUCT_ID!r})."
            ),
        )

    # Dev mode skips signature checking so local tests and CI don't need
    # the production private key. Production builds must NEVER set this.
    dev_mode = os.environ.get("CHAINLADDER_LICENSE_DEV_MODE") == "1"
    if not dev_mode and not _verify_signature(data):
        return LicenseStatus(
            active=False,
            owner=data.get("owner"),
            expires=int(data["expires"]) if data.get("expires") else None,
            message=(
                "License file signature is missing or invalid. "
                "If this is a fresh purchase, verify you downloaded the "
                "exact file the seller emailed (no copy-paste). "
                f"If problems persist, contact support via {UPGRADE_URL}."
            ),
        )

    expires = data.get("expires")
    if expires is not None and time.time() > float(expires):
        return LicenseStatus(
            active=False,
            owner=data.get("owner"),
            expires=int(expires),
            message=(
                f"Your Pro license expired at "
                f"{time.strftime('%Y-%m-%d', time.gmtime(int(expires)))}. "
                f"Renew at {UPGRADE_URL}."
            ),
        )

    return LicenseStatus(
        active=True,
        owner=data.get("owner"),
        expires=int(expires) if expires is not None else None,
        message=(
            f"Pro license active for {data.get('owner', 'unknown owner')}"
            + (
                "."
                if expires is None
                else f", expires {time.strftime('%Y-%m-%d', time.gmtime(int(expires)))}."
            )
        ),
    )


def require_pro_or_explain() -> dict[str, object] | None:
    """Return a tool-style error dict when no Pro license is active; return
    `None` when the caller is free to proceed."""
    status = check_pro_license()
    if status.active:
        return None
    return {
        "error":   "pro_license_required",
        "status":  status.to_dict(),
    }
