# Keygen — issuing mcp-chainladder Pro licenses

> ⚠️ **For sellers only.** This directory contains the private key that
> mints Pro licenses. Treat it like a production credential — anyone
> with it can issue licenses indistinguishable from yours. **Never
> commit `PRIVATE_KEY.txt`.** It's in the repo's `.gitignore`, but
> double-check before any push.

## How it fits together

```
┌──────────────────────────┐         ┌────────────────────────────┐
│ keygen/cl_keygen.py      │         │ src/mcp_chainladder/        │
│ (this folder, stays      │         │   license.py                │
│ on seller's machine)     │         │ (ships to every buyer       │
│                          │         │ via PyPI)                   │
│ + PRIVATE_KEY.txt        │         │                             │
│   (32-byte ed25519,      │ signs   │ PUBLIC_KEY_B64 = "rk7K…"    │
│   never published)       ├────────►│ Verifies signature using    │
│                          │         │ embedded public key.        │
└──────────────────────────┘         └────────────────────────────┘
```

The seller signs license files with the **private** key; every buyer's
installed `mcp-chainladder` verifies them with the matching **public**
key. Bypassing this requires modifying the public key in the
verifier's source, which any user has the right to do — the goal is
to make casual sharing inconvenient enough that honest buyers buy,
not to be NSA-grade.

## Set up your private key (one-time)

The repo ships with a demo keypair so the tests can run locally. **You
should generate fresh keys before going to production.**

```bash
# Generate a new keypair.
python3 - <<'EOF'
import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, PublicFormat, NoEncryption,
)
priv = Ed25519PrivateKey.generate()
pub  = priv.public_key()
priv_raw = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
pub_raw  = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
print("PUBLIC_KEY_B64  =", base64.b64encode(pub_raw).decode())
print("PRIVATE_KEY_B64 =", base64.b64encode(priv_raw).decode())
EOF
```

Then:

1. Copy `PUBLIC_KEY_B64` into `src/mcp_chainladder/license.py`
   (replace the existing `PUBLIC_KEY_B64 = "…"` line).
2. Save `PRIVATE_KEY_B64` into `keygen/PRIVATE_KEY.txt`:
   ```bash
   echo "PASTE_PRIVATE_KEY_HERE" > keygen/PRIVATE_KEY.txt
   chmod 600 keygen/PRIVATE_KEY.txt
   ```
3. Bump the package version in `pyproject.toml` and re-publish to
   PyPI. Existing customers' license files were signed with the **old**
   private key, so rotating keys invalidates their licenses — either
   re-issue them all, or version-gate the verifier (e.g. by
   maintaining a list of valid public keys).

## Issue a license

```bash
# Perpetual (no expiry)
python3 keygen/cl_keygen.py \
    --owner alice@example.com \
    --key   CL-PRO-2026-0001 \
    --output licenses/alice.license

# Time-limited
python3 keygen/cl_keygen.py \
    --owner bob@example.com \
    --key   CL-PRO-2026-0002 \
    --expires 2027-12-31 \
    --output licenses/bob.license

# Sanity-check an existing file
python3 keygen/cl_keygen.py --verify licenses/alice.license
```

Email the `.license` file to the buyer with installation instructions:

> Save the attached file as `~/.chainladder/license` (create the
> directory if it doesn't exist) and restart Claude Desktop. Run
> `pro_license_status` to confirm it's active.

## Stripe webhook integration (optional)

For a fully-automated post-purchase flow:

1. Set up a Stripe webhook at `https://your-domain/cl-pro/webhook`
   listening for `checkout.session.completed` events.
2. In your webhook handler, call `cl_keygen.py` (or use it as a
   library — `from cl_keygen import issue_license`) to generate the
   `.license` file.
3. Email the file to `event.customer_details.email` using a
   transactional service (Postmark, SendGrid, Resend, etc.).

A minimal Flask sketch:

```python
import json
from pathlib import Path
import stripe
from flask import Flask, request

# Make sure the seller's private key is available — either via
# CL_KEYGEN_PRIVATE_KEY env var or keygen/PRIVATE_KEY.txt next to
# this script.
from cl_keygen import issue_license

stripe.api_key                 = "sk_live_…"
WEBHOOK_SECRET                 = "whsec_…"

app = Flask(__name__)

@app.post("/cl-pro/webhook")
def webhook():
    payload    = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)

    if event["type"] != "checkout.session.completed":
        return "", 200
    session = event["data"]["object"]
    email   = session["customer_details"]["email"]
    order   = session["id"]                                # use as the license key
    license = issue_license(owner=email, key=order, expires_ts=None)

    # Save + email
    out = Path("licenses") / f"{order}.license"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(license, indent=2, sort_keys=True))
    send_license_email(email, out)                         # ← your email sender
    return "", 200
```

`send_license_email` is your business — Postmark templates work well
because the attachment is small (<1 KB).

## What "Pro" gates today (v1.2)

| Tool | Notes |
|---|---|
| `bornhuetter_ferguson` | BF method with side-by-side CL comparison |
| `interpret_diagnostics` | Mack tests with verdict labels + recommendations |
| `sensitivity_analysis` | Drop-one-out IBNR impact ranking |
| `tail_extrapolation` | Exponential + inverse-power tail fits |
| `compare_methods` | CL + BF in one call with delta interpretation |

Future Pro tools (v1.3+ roadmap): `generate_pdf_report`,
`batch_csv_processing`, `cape_cod`, `mack_bf`.

## CI-friendly testing without the private key

Set `CHAINLADDER_LICENSE_DEV_MODE=1` and the verifier accepts unsigned
license files. The Pro test suite uses this so contributors don't
need access to the production signing key.

**Never set this env var in a production build.** The Pro gate
becomes purely advisory if you do.
