# Publishing `mcp-chainladder` to PyPI

End-to-end script. Estimated total time: 15 minutes for a first
release, 30 seconds for each subsequent version bump.

## One-time setup

### 1. Create accounts

- **PyPI** (production): <https://pypi.org/account/register/> — verify the email
- **TestPyPI** (staging, recommended for the first release): <https://test.pypi.org/account/register/>

Both require **2FA** (TOTP app or hardware key). Set it up at registration.

### 2. Generate API tokens

PyPI no longer accepts username/password for uploads. Generate a token:

- PyPI → **Account settings → API tokens → Add API token**
  - Name: `mcp-chainladder-upload`
  - Scope: **Entire account** (you'll narrow it after the first upload)
- Copy the `pypi-…` token immediately — PyPI shows it once.

Do the same on TestPyPI. Treat both tokens as passwords.

### 3. Install `twine`

```bash
python3 -m pip install --user --upgrade twine
```

### 4. Stash tokens in `~/.pypirc`

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmc…    # your real token

[testpypi]
username = __token__
password = pypi-AgENdGVzdC5weXBpLm9yZw…
```

`chmod 600 ~/.pypirc` so it's owner-readable only.

---

## Release flow

### Dry run on TestPyPI first

The dist artifacts are already built (`./dist/mcp_chainladder-1.0.0-*`):

```bash
cd /Users/jn/Desktop/omni/mcp-chainladder
python3 -m twine upload --repository testpypi dist/*
```

You should see a URL like `https://test.pypi.org/project/mcp-chainladder/1.0.0/`.
Visit it — it'll render the README and confirm the version is live.

Test-install from TestPyPI in a clean venv:

```bash
python3 -m venv /tmp/clcheck
/tmp/clcheck/bin/pip install \
    --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    mcp-chainladder
/tmp/clcheck/bin/mcp-chainladder --help 2>&1 | head -5
```

`--extra-index-url` covers the runtime deps (`mcp` etc.) that live on
real PyPI, not TestPyPI.

### Publish to real PyPI

When the TestPyPI install looks right:

```bash
python3 -m twine upload dist/*
```

That's it. `mcp-chainladder` is live at
<https://pypi.org/project/mcp-chainladder/> immediately. Users can
install with:

```bash
pipx install mcp-chainladder
# or, for ephemeral use:
uvx mcp-chainladder
```

---

## Subsequent releases

```bash
# 1. Bump the version in pyproject.toml (semver)
sed -i '' 's/version = "1.0.0"/version = "1.0.1"/' pyproject.toml

# 2. Build
rm -rf dist/ build/ *.egg-info
python3 -m build

# 3. Sanity-check the new artifacts
python3 -m twine check dist/*

# 4. Upload
python3 -m twine upload dist/*
```

PyPI rejects re-uploads of the same version, so always bump first.

---

## Failure modes you might hit

| Symptom | Fix |
|---|---|
| `403 Forbidden — Project does not exist` | The project doesn't yet — the first `twine upload` creates it. Make sure your token has **Entire account** scope on the first upload; you can narrow it to `mcp-chainladder` after. |
| `403 Forbidden — invalid token` | Re-paste the token. If it still fails, regenerate. |
| `400 Bad Request — File already exists` | You can't re-upload the same version. Bump the version in `pyproject.toml` and rebuild. |
| `README on PyPI looks broken` | `python3 -m twine check dist/*` shows the rST/MD renderer's complaints. Fix and re-upload a new version. |
| `Long description content type missing` | Make sure `pyproject.toml` has `readme = "README.md"`; ours does. |

---

## After first release

- Narrow the token: PyPI → **API tokens** → revoke the entire-account
  one, create a new one scoped to `mcp-chainladder`.
- Hook up GitHub Actions for auto-publish on tag push (see
  [`.github/workflows/publish.yml`](https://github.com/pypa/sampleproject/blob/main/.github/workflows/publish.yml)
  for a copy-paste template).
- Reserve the brand: PyPI projects are first-come-first-served. If you
  later rename to `chainladder-mcp`, register both names and have one
  redirect to the other via a thin stub package.
