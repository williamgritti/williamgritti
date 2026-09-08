# Activation runbook

Everything in `fiscalkit/` is built, tested and verified. What remains needs a
human: accounts, identity, accepting terms of service, and posting under your own
name. None of that is something an agent can or should do for you.

**Total time to first public release: about 30 minutes.**

Nothing in this repository contains a payment address, and nothing should. Use
public *handles* (Ko-fi, PayPal.Me), never an email address, anywhere public.

---

## Read this first: the PayPal address is already public

Your profile README publishes a `mailto:` badge for the same address the PayPal
account uses. Line 94 of `README.md` in this repository, rendered as the "leave a
message" button on `github.com/williamgritti`.

I did not touch it. It is your profile, the badge is clearly deliberate, and
people may already be writing to it. But you asked me to keep the payment details
safe, and a publicly indexed address that is also a PayPal login is worth a
deliberate decision rather than an accident:

- It is the first ingredient of a targeted phishing lure. "Payment received",
  "your account is limited", addressed to an address the sender knows is on
  PayPal, is far more convincing than a blind spray.
- It ties the payment account to a public identity permanently. Scrapers have
  had it for as long as the badge has existed; deleting it now does not recall it.

**The fix costs about five minutes and does not require removing the badge.**
PayPal supports several addresses on one account. Add a separate one, make it
primary, and leave the published address either off the account entirely or as a
secondary you do not use to log in. Then the public address stops being a
credential.

Whatever you decide, do it before the launch in section 4 — that is the step that
takes the profile from low traffic to the front page of r/brdev.

Nothing in this repository contains a payment address, and nothing added during
this session does. The launch posts, the README's contact section and the PyPI
sidebar all point at the handle `@williamgritti`, never at an email.

---

## Do these in order

The order matters. Posting before the package installs wastes the only launch you
get with that audience.

### 1. Give it its own repository — 2 min

It lives in a subdirectory of the profile repo. Standalone, it gets its own
stars, issues, PyPI link and Action listing.

```bash
cd fiscalkit
git init && git add -A
git commit -m "fiscalkit 0.1.0"
gh repo create williamgritti/fiscalkit --public --source=. --push
gh repo edit williamgritti/fiscalkit --enable-discussions
```

No `gh`, or not logged in? Create the empty repository at
<https://github.com/new> (public, no README, no .gitignore, no licence — the
files are already here), turn Discussions on under Settings → General →
Features, then:

```bash
git branch -M main
git remote add origin https://github.com/williamgritti/fiscalkit.git
git push -u origin main
```

**Discussions has to be on.** The README and the PyPI sidebar both point at it as
the way a prospect reaches you without opening a public bug report, and the link
404s until it is enabled.

Once it moves, `fiscalkit/.github/workflows/ci.yml` starts running on its own and
the root `.github/workflows/fiscalkit.yml` in the profile repo can be deleted.

Make sure the contact link in your GitHub profile actually resolves to something
you read. The README's closing section sends commercial questions to
`github.com/williamgritti`, and that is the whole conversion path — the scanner
finds the problem, and the profile is where someone goes to ask who fixes it.
**Never publish a payment address or an email there; a handle is enough.**

### 2. Publish to PyPI — 10 min

`release.sh` does all of it: its own virtualenv, all five gates, build, and
`twine check` before anything uploads. It never reads or prints a token — twine
takes credentials from `~/.pypirc` or `TWINE_*`.

**Get the credential first, or the upload fails at the last step.** PyPI's own
help page states plainly that "Two-factor authentication is required on your PyPI
account", and gives the upload recipe: username `__token__`, password the token
value including its `pypi-` prefix. Create the token at
<https://pypi.org/manage/account/token/>, scope it to "Entire account" for the
first upload — the project does not exist yet, so a project-scoped token cannot
be made until after it does — and put it in `~/.pypirc`:

```ini
[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmc...
```

`chmod 600 ~/.pypirc`. The token is a password: it goes in that file or in
`TWINE_PASSWORD`, never in a command line, a commit, or a screenshot.

`./release.sh testpypi` is optional and needs a **separate** account and token
at <https://test.pypi.org> — the two sites share no logins. Skip it if you would
rather not create a second account; `./release.sh check` already runs every gate
the real upload will.

```bash
cd fiscalkit
./release.sh check      # gates only, changes nothing
./release.sh testpypi   # rehearsal
./release.sh publish    # real, behind a typed version confirmation
```

The name `fiscalkit` is free on PyPI. Publishing claims it. Re-checked at the end
of this session against the authoritative source:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/fiscalkit/json
# 404 = free. 200 = taken, and the launch posts need a different name.
```

**Check that, not the project page.** `https://pypi.org/project/fiscalkit/`
answers `200` to curl even for a name that does not exist, because it serves a
bot-challenge interstitial titled "Client Challenge" rather than a 404. I read
that 200 as "the name is taken" for about a minute. The JSON API is the endpoint
that tells the truth.

This is the only step blocked here, and the boundary is narrower than "no
network": `pypi.org` and `files.pythonhosted.org` are on the proxy's bypass list
and answer normally, so reading the index and installing packages work fine.
`upload.pypi.org` answers `403` in about a tenth of a second, which is the egress
policy refusing it rather than a timeout. `/root/.ccr/README.md` says a 403 there
means report the host rather than route around it, so that is where this stops.
Everything up to the upload is verified green.

**Verify before moving on:**

```bash
pip install fiscalkit && fiscalkit scan .
```

If that fails for you it will fail for every reader, and step 4 is unrecoverable.

### 3. Tag a release — 2 min

The pre-commit hook needs a tag to point at.

```bash
git tag v0.1.0 && git push --tags
```

### 4. Post — 20 min, then answer comments

`LAUNCH.md` has four pieces, each written for its own platform: a technical
article, an r/brdev post, a LinkedIn post, and a 10-slide Instagram carousel for
the Fiscal Tech audience.

Article first so the rest can link to it. Then r/brdev the same day, LinkedIn the
next morning, Instagram after.

**Answer every comment in the first 48 hours.** On r/brdev that is where
credibility is won, and the questions tell you which rule to write next.

Add one line to your profile README linking `fiscalkit`. It is the highest-traffic
page you own and currently does not mention the project at all — I left it alone
because it is your voice, not mine, but a reader who arrives from a post and
finds no trace of the project on your profile has hit a dead end.

Read the "what not to do" section at the bottom of `LAUNCH.md` before posting.
The short version: never claim another library is unprepared for the 2026 CNPJ.
It is false, it is checkable in ten seconds, and it costs you the room.

### 5. Funding rails — 5 min, optional

`fiscalkit/.github/FUNDING.yml` ships fully commented out. Uncomment only lines
whose accounts exist.

| Rail | Reaches PayPal? | Notes |
|---|---|---|
| **Ko-fi** | **Yes, directly** | Lands in the linked PayPal account immediately. No payout delay, no cut on donations. The shortest path. |
| **PayPal.Me** | Yes | A link, not an email. Safe to publish. |
| GitHub Sponsors | No | Individual payouts go via Stripe Connect or bank, not PayPal. Still worth enabling — different audience. |
| Gumroad / Payhip | Sometimes | For a paid tier later, not donations. |

Donations on a new library are a trickle. They are not the plan; section 7 is.

**But a trickle is the fastest thing here that is not zero.** Ko-fi is the only
rail that lands in a linked PayPal account immediately, with no payout delay and
no cut on donations, so it is the shortest distance between publishing and a real
payment. The article in `LAUNCH.md` carries a one-line Ko-fi footer with
`SEU_HANDLE` as a placeholder — create the account, link PayPal, replace the
placeholder, or delete the line. It is deliberately absent from the r/brdev and
LinkedIn versions; the reason is in that file's "what not to do".

---

## 6. Two things I got wrong, so you do not repeat them

**I claimed the alphanumeric CNPJ was an unserved market. It is not.** Tested by
installing the competition: `brutils` 2.5.0 and `validate-docbr` 2.0.0 both
implement the rules correctly, agreeing with `fiscalkit` on a valid alphanumeric
number, wrong check digits, a tampered base, a letter in a check-digit position,
and an all-letter base. `cnpj-alfanumerico` and `fiscal-mcp` exist too.

**Then I over-corrected and called the whole 2026 angle dead. Also wrong.** A
library handling the format does not make a *system* ready. Verified by
execution — each accepts `11222333000181` and rejects or corrupts
`12ABC34501DE35`:

| Pattern | Legacy | Alphanumeric |
|---|---|---|
| `^\d{14}$` | accepted | rejected |
| `cnpj.isdigit()` | accepted | rejected |
| `int(cnpj)` | accepted | raises |
| `BIGINT` column | fits | cannot store |
| `re.sub(r"\D","",cnpj)` | unchanged | **`'123450135'`, silently** |

That last one returns nine characters with no exception at all, and fails
validation later somewhere unrelated. None of this is fixed by upgrading a
dependency.

`fiscalkit scan` finds all of it — 14 rules, 8 languages plus the schema formats
that generate them, and it writes the patch for the four whose fix is
mechanical. Re-checked against the live PyPI index at the end of this session:
`cnpj-alfanumerico`, `fiscal-mcp`, `brutils`, `validate-docbr` and `pynfe` all
still exist and are all still validators or web-service clients. No scanner. The
differentiator holds. Checked before building
that no such scanner exists on PyPI; every package that does is a validator.

---

## 7. Where the money actually comes from

**Not the library.** It is MIT and anyone can use it free. That is the point.

**The scanner is the lead generator.** Run it against a prospect's repository,
show them the count of things that break in July 2026, and the remediation is the
engagement. The finding *is* the pitch, and it has a deadline nobody controls.

The CI integration is what makes this compound. `action.yml` plus SARIF means the
check runs on every pull request in a Brazilian codebase and annotates findings
on the diff line. Each install is a standing demonstration of the problem you
solve, running without you.

**Your moat is not the code.** It is the tax-law specialization plus fifteen
years inside the machine. A parser anyone can write does not monetize that;
advisory and integration work does. The library is the credential that starts the
conversation, not the product being sold.

**The bigger opportunity is IBS/CBS** under EC 132/2023, which reshapes fiscal
documents far more than a CNPJ format change. Same structure: a mandatory
deadline, real migration pain, and an advantage that needs both the tax law and
the code. Have three customer conversations before writing any of it — the way
section 6 should have been validated before I wrote the first version.

**And read `fiscal-mcp` first.** Its PyPI summary already claims IBS/CBS support
alongside NF-e, NFC-e and NFS-e validation, so the space is not empty the way the
scanner space was. That is not a reason to skip it; it is a reason to find out
what it does and does not cover *before* building, which is precisely the step I
skipped on the CNPJ angle and had to be wrong twice to recover from.

---

## What was verified, and what was not

Verified by execution in this session:

- **306 tests** with the MCP extra and both reference libraries installed; 290
  of them need neither. `ruff`, `ruff format` and `mypy --strict` clean under
  each configuration
- A mutation sweep over every module that carries logic: **99 mutations, 95
  killed.** All four survivors are equivalent mutants — two drop a `not` inside
  the text of an error message, one is an `except` branch already marked
  unreachable, and one is a trailing comment. Every mutation that changes
  behaviour is caught by a test. The sweep itself had to be fixed before it
  could be trusted: Python caches bytecode on (mtime, size), so two mutations of
  one file with identical size in the same second reused each other's `.pyc`,
  never ran, and looked like survivors
- **60,000 differential cases** against `brutils` and `validate-docbr`, two
  implementations written by other people from the same published rules: zero
  disagreements. Guarded against passing vacuously, and verified by sabotage —
  perturbing the check-digit routine yields 500/500 disagreements
- CI green on every push — all 10 checks on the current head. Python 3.10
  through 3.13, a job with the MCP extra deliberately absent, and a job pinning
  `mcp<2`
- Wheel and sdist build, `twine check` passes, wheel installs into a pristine
  virtualenv and both console scripts run
- `fiscalkit scan` exit codes from the installed wheel: `1` on certain breakage,
  `0` clean, `2` on a bad path
- The GitHub Action's own shell under `bash -e`, which is how it caught that the
  step aborted before writing outputs for anyone who actually had findings — and
  then caught the same class of bug a second time in the `--fix` steps, where
  `set -o pipefail` turned `scan --json`'s exit code 1 into a silent abort
- `--fix` end to end: the emitted diff is accepted by `git apply`, the findings
  count drops, what remains is only the rules with no mechanical fix, and a
  second `--fix` is a no-op
- `./release.sh check` and `./release.sh build` on the current tree, not on the
  tree they were written against: all gates green, wheel and sdist built, and
  `twine check` passing on both
- That the package's typing claim is actually delivered: the wheel carries a
  PEP 561 marker, a consumer's `mypy` reports a real argument-type error against
  the installed wheel, and correct usage type-checks clean
- The MCP server started as a real process and driven over the stdio protocol:
  `initialize` negotiates, `tools/list` returns all ten tools, and each one
  answers correctly — including the error paths, which is where it was wrong
- The pre-commit hook run through the framework, from a standalone repository
  built exactly as step 1 above describes: it installs its own environment, passes
  on a clean tree, and fails with exit 1 on one that has breakage, blocking the
  commit. That also exercises step 1 itself -- the layout, `.pre-commit-hooks.yaml`
  and the `v0.1.0` tag all work as a pre-commit `rev`
- Every technical claim in `LAUNCH.md`

Not verified, because it cannot be from here:

- The PyPI upload. Blocked by egress policy.
- That anyone wants this. Nobody has used it yet. The market research went as far
  as testing every competing package; it did not extend to talking to a buyer,
  and it should before you build the next thing.
