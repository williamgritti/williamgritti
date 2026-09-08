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

**Read this before pitching anything.** My original thesis for this package was
that the July 2026 alphanumeric CNPJ deadline was an unserved market. I tested
that assumption by installing the competition, and **it is false**:

- `brutils` 2.5.0 and `validate-docbr` 2.0.0 already implement the alphanumeric
  CNPJ rules correctly — verified against valid values, wrong check digits,
  tampered bases and letters in check-digit positions. All five edge cases match
  `fiscalkit` exactly.
- `fiscal-mcp` 0.2.1 already exists and is the same concept as this package's MCP
  server, and broader: official XSD validation, NFS-e, and IBS/CBS.

So do not sell "we support the 2026 CNPJ and others don't." Any Brazilian dev
will check in thirty seconds and you will lose the room.

What is actually true and defensible:

- **The code is genuinely good** — zero dependencies, `mypy --strict`, 117 tests,
  `Decimal` money, an honest treatment of the check-digit weakness. It is a
  credible public work sample.
- **Access-key decoding is a real gap** in the general-purpose libraries.
  `brutils` has nothing for it.
- **Your moat is not the library.** It is the tax-law specialization plus fifteen
  years inside the machine. A commodity parser does not monetize that; advisory
  and integration work does. The library is the credential that makes the
  conversation happen, not the product.

The larger deadline-driven change worth studying is the **IBS/CBS transition**
under EC 132/2023, which reshapes fiscal documents far more than the CNPJ format
does. That is where a tax-law-plus-Python specialist has a durable advantage.
Validate demand before building, the way this section should have been validated
first.

## 5. Distribution, when you want it

Blocked from this sandbox, all straightforward from your machine: the
`r/brdev` and `r/Python` communities, the `awesome-mcp-servers` list, the
Brazilian dev Discords, and a short post on the alphanumeric CNPJ change — that
last one is genuinely useful content and it is on a deadline everyone shares.
