# Activation checklist

`fiscalkit/` is finished and shippable. Everything below is the part that needs a
human: it requires accounts, identity, and accepting terms of service, none of
which an agent can or should do on your behalf.

Nothing in this repository contains a payment address, and nothing should. Use
public *handles* (Ko-fi, PayPal.Me) rather than an email address anywhere public.

## 1. Give it its own repository (2 min)

The library currently lives in a subdirectory of the profile repo. It wants to be
standalone so it gets its own stars, issues and PyPI link.

```bash
# from a clone of this branch
cd fiscalkit
git init && git add -A
git commit -m "fiscalkit 0.1.0"
gh repo create williamgritti/fiscalkit --public --source=. --push
```

## 2. Publish to PyPI (10 min)

The wheel and sdist already build cleanly — this sandbox blocks `upload.pypi.org`,
so the upload is the one step left.

```bash
pip install build twine
python -m build
twine upload dist/*        # needs a PyPI API token
```

Publish to TestPyPI first if you want a dry run. Once live, `pip install
fiscalkit` works for everyone, and the README badge resolves.

## 3. Turn on the funding rails (5 min)

`fiscalkit/.github/FUNDING.yml` ships with every line commented out. Uncomment
only the ones whose accounts exist.

The relevant fact for routing money to PayPal:

| Rail | Reaches PayPal? | Notes |
|---|---|---|
| **Ko-fi** | **Yes, directly** | Payments land in the linked PayPal account immediately. No payout delay, no cut on donations. This is the shortest path. |
| **PayPal.Me** | Yes | A link, not an email. Safe to publish. |
| GitHub Sponsors | No | Individual payouts go via Stripe Connect or bank transfer, not PayPal. Still worth enabling — different audience. |
| Gumroad / Payhip | Sometimes | Useful later if you sell a paid tier rather than take donations. |

Create the Ko-fi account, link it to your PayPal, then uncomment the `ko_fi:`
line with your handle.

## 4. Where the money actually comes from

Donations on a new library are a trickle. The realistic revenue is the paid tier
this makes credible, and you already have the distribution for it:

- **The 2026 alphanumeric CNPJ is a forcing function.** Every Brazilian system
  that validates a CNPJ has to change before July 2026. `fiscalkit` already
  handles it; most libraries reject it outright. That is a migration consulting
  offer with a hard deadline attached, aimed at exactly the market fiscaltech.dev
  already sells to.
- **The OSS core is the credential.** It shows the tax-law-plus-Python
  combination in public, which is the thing that is genuinely hard to copy.
- **The paid layer** is the part that does not belong in the free library: a
  hosted batch API, SEFAZ querying with certificate handling, ERP connectors,
  and support with an SLA.

## 5. Distribution, when you want it

Blocked from this sandbox, all straightforward from your machine: the
`r/brdev` and `r/Python` communities, the `awesome-mcp-servers` list, the
Brazilian dev Discords, and a short post on the alphanumeric CNPJ change — that
last one is genuinely useful content and it is on a deadline everyone shares.
