# GitHub repo + CI setup

Five minutes from a directory on your Mac to a published GitHub repo
with CI running on every push and PyPI auto-publishing on every tag.

## Prerequisites

- A GitHub account
- `gh` CLI installed and authenticated: `brew install gh && gh auth login`
- (Optional) A PyPI account + API token (see `PYPI_PUBLISH.md`)

## Initialize and push

```bash
cd /Users/jn/Desktop/omni/mcp-chainladder

# Initialise the local repo.
git init
git add .
git status                                   # double-check nothing
                                              # like PRIVATE_KEY.txt is staged

# Sanity check: PRIVATE_KEY.txt must NOT appear in the staged file list.
# If it does, abort and fix .gitignore before continuing.
if git diff --cached --name-only | grep -q PRIVATE_KEY; then
    echo "STOP — PRIVATE_KEY.txt is about to be committed. Aborting."; exit 1
fi

git commit -m "Initial commit — mcp-chainladder v1.2.0"

# Create the GitHub repo + push.
gh repo create datalattice/mcp-chainladder \
    --public \
    --description "MCP server for actuarial chain-ladder reserving — factors, IBNR, Mack stats, diagnostics, BF, and more." \
    --source=. \
    --remote=origin \
    --push

# Tag and push the first release.
git tag v1.2.0
git push origin v1.2.0
```

That last `git push origin v1.2.0` triggers `.github/workflows/publish.yml`,
which builds and uploads to PyPI. **But first**: configure the PyPI token
as a repo secret.

## One-time GitHub secrets

In the repo's web UI:

1. **Settings → Secrets and variables → Actions → New repository secret**
2. Name: `PYPI_API_TOKEN`
3. Value: paste your PyPI API token (the `pypi-…` string from
   <https://pypi.org/manage/account/token/>)
4. **Save**

Without this secret the publish workflow fails at the last step
(twine upload), but builds and tests still run on every push.

## Recommended branch protection

```
Settings → Branches → Add rule for main:
  ☑ Require status checks to pass before merging
    └─ Required: Test (the workflow from .github/workflows/test.yml)
  ☑ Require linear history     (cleaner release history)
  ☑ Do not allow bypassing the above settings
```

Optional but tidy: enable auto-merge so PRs that pass CI merge themselves.

## Subsequent releases

```bash
# 1. Bump versions in pyproject.toml AND src/mcp_chainladder/__init__.py
# 2. Commit, tag, push
git commit -am "Release v1.2.1"
git tag    v1.2.1
git push   origin main --tags
```

Watch the **Actions** tab for the publish workflow to go green. PyPI
takes ~30 seconds; users can `pipx install mcp-chainladder --upgrade`
right after.

## Things to do manually after the first push

- [ ] **Repo description + topics**: GitHub repo → ⚙ → set topics
      `mcp`, `claude`, `actuarial`, `reserving`, `chain-ladder`, `python`
- [ ] **About section**: add the URL of your marketing site (or
      <https://chainladder.app> when it exists)
- [ ] **README badges**: PyPI version, Python versions, license, CI
      status — already templated in the README; they'll go live once
      the package is on PyPI and the repo public
- [ ] **Issue templates**: GitHub auto-suggests these once the repo is
      live; the defaults are fine
- [ ] **Privacy + Discussions**: enable Discussions if you want a
      forum-style support venue (lower-friction than issues)
- [ ] **Sponsor button**: GitHub Sponsors or a Buy Me a Coffee link —
      good for the freemium audience that doesn't want to deal with a
      full purchase flow

## Where the keygen actually lives (operational guidance)

Three options, in order of operational complexity:

### Option 1 — manual issuance (start here)

Keep `keygen/cl_keygen.py` + `keygen/PRIVATE_KEY.txt` on a single
trusted machine (your laptop). When a Stripe receipt arrives, you
run the command and email the file back. Total monthly admin: ~5
minutes per 10 customers.

Pros: zero infra, zero risk of key exposure online.
Cons: doesn't scale past ~50 customers/month.

### Option 2 — webhook-driven (50+ customers/month)

Deploy a small Flask / FastAPI app on Fly.io / Render / Railway that
listens for `checkout.session.completed` webhooks from Stripe.
`keygen/PRIVATE_KEY.txt` lives as a secret in the platform's
environment. See `keygen/README.md` for a sketch.

Pros: zero-touch fulfilment.
Cons: a service that holds the signing key — protect it like the
production credential it is.

### Option 3 — Smithery / Lemon Squeezy / Paddle license keys (sell + dist via 3rd party)

Some marketplaces handle license keys natively. If you list on Smithery
Pro, their licensing flow can issue keys that `license.py` accepts
(format-compatible). Trade some margin (~5–10%) for not running infra.

Pros: someone else runs the checkout + keygen.
Cons: an additional middleman; tied to a specific marketplace.

My recommendation: ship Option 1, watch the inbound for a month,
upgrade to Option 2 once volume justifies it.
