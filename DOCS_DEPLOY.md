# Deploying the marketing site

The `docs/` folder is a complete static site — five pages (index,
install, pro, privacy, plus auxiliary `sitemap.xml` / `robots.txt`),
zero JavaScript, zero remote dependencies, system fonts only. It's
ready to go live behind GitHub Pages with one workflow run.

## Quick start (github.io subdomain)

After you've followed `REPO_SETUP.md` to create the repo:

1. **Push at least once** so the `docs/` folder is on `main`.
2. **GitHub repo → Settings → Pages**
3. **Source**: set to **GitHub Actions**
4. The `.github/workflows/pages.yml` workflow that ships with this repo
   takes over on the next push and publishes to:

   ```
   https://<your-user-or-org>.github.io/mcp-chainladder/
   ```

5. Every subsequent push to `main` that touches `docs/` or the
   workflow file redeploys automatically (usually < 30 seconds).

If you want to trigger a deploy without changing files, go to **Actions
→ Deploy GitHub Pages → Run workflow**.

## Going live at `chainladder.app` (custom domain)

The `docs/CNAME` file in this repo already points at `chainladder.app`.
To activate it:

1. **Buy the domain** somewhere. Cloudflare, Namecheap, Porkbun — any
   registrar; ~$15/year for `.app`.
2. **At your DNS provider**, add these records:

   | Type  | Name | Value |
   |-------|------|-------|
   | A     | @    | 185.199.108.153 |
   | A     | @    | 185.199.109.153 |
   | A     | @    | 185.199.110.153 |
   | A     | @    | 185.199.111.153 |
   | CNAME | www  | <your-user>.github.io |

   (Those four A records are GitHub Pages' anycast IPs; copy-pasteable.)
3. **GitHub repo → Settings → Pages → Custom domain**: paste
   `chainladder.app` and click Save.
4. Wait for the **green check mark** ("DNS check successful"). This
   takes anywhere from 1 minute to 1 hour depending on your
   registrar's TTL.
5. Tick **Enforce HTTPS** once the certificate provisions (usually
   another 10–60 minutes after step 4).

That's it. The site is now at `https://chainladder.app` and
`https://www.chainladder.app` (which redirects to the apex).

## Don't want a custom domain?

Delete `docs/CNAME`. The site stays accessible at the
`<your-user>.github.io/mcp-chainladder/` URL. Update the README +
in-package URLs (`UPGRADE_URL` in `license.py`, the homepage URL in
`pyproject.toml`) to point there instead.

## After the first deploy — placeholders to replace

A few strings in the templates are stand-ins. Search-and-replace
before going live:

| Find | Replace with |
|------|--------------|
| `https://buy.stripe.com/chainladder-pro` | Your real checkout URL |
| `support@chainladder.app` | Your real support email |
| `dataanalyticsactuary/mcp-chainladder` | Your real GitHub org/repo |
| `https://chainladder.app/` | Your real homepage URL (only matters if you use a domain other than `chainladder.app`) |

```bash
# Quick search:
grep -rn "chainladder-pro\|support@chainladder\|dataanalyticsactuary" docs/
```

## Page-level testing

Before pushing, preview the site locally:

```bash
cd docs/
python3 -m http.server 8000
# open http://localhost:8000 in a browser
```

Things to spot-check:

- All four pages render with the brand styling
- The nav links work in both directions
- Dark mode kicks in when your OS is set to Dark
- The Buy Pro CTA goes to your real Stripe URL (after replacing the
  placeholder above)
- Mobile width — narrow the browser to ~360px wide; the layout should
  collapse to single-column

## Performance + privacy properties

The site loads **everything from your own domain**:

- No web fonts (system stack only)
- No JavaScript at all
- No tracking pixels, no analytics
- No third-party scripts, including no Google Tag Manager

That means:
- Lighthouse score should be 100/100 across the board
- It's compliant with cookieless / no-consent privacy regimes by
  default (GDPR, ePrivacy, etc.)
- Your privacy policy at `/privacy.html` is *literally true*, which
  is a refreshing change from most marketing sites

If you do want analytics later, the cleanest options are:

- [Plausible](https://plausible.io) — self-hostable, no cookies, GDPR
  compliant out of the box. Drop one `<script>` in `index.html`.
- [Fathom](https://usefathom.com) — same shape, paid SaaS.
- Server logs from your registrar if Cloudflare is in front of it.

Avoid Google Analytics — it'll break your "Data Not Collected" claim
on the App Store and Anthropic privacy labels.
