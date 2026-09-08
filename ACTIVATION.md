# Activation runbook

Everything in `fiscalkit/` is built, tested and verified. What remains needs a
human: accounts, identity, accepting terms of service, and posting under your own
name. None of that is something an agent can or should do for you.

**Total time to first public release: about 30 minutes.**

Nothing in this repository contains a payment address, and nothing should. Use
public *handles* (Ko-fi, PayPal.Me), never an email address, anywhere public.

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
```

Once it moves, `fiscalkit/.github/workflows/ci.yml` starts running on its own and
the root `.github/workflows/fiscalkit.yml` in the profile repo can be deleted.

### 2. Publish to PyPI — 10 min

`release.sh` does all of it: its own virtualenv, all five gates, build, and
`twine check` before anything uploads. It never reads or prints a token — twine
takes credentials from `~/.pypirc` or `TWINE_*`.

```bash
cd fiscalkit
./release.sh check      # gates only, changes nothing
./release.sh testpypi   # rehearsal
./release.sh publish    # real, behind a typed version confirmation
```

The name `fiscalkit` was free on PyPI during this session. Publishing claims it.
This is the only step that was blocked here — the sandbox refuses
`upload.pypi.org` — and everything up to it is verified green.

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
mechanical. Checked before building
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

---

## What was verified, and what was not

Verified by execution in this session:

- **281 tests** across the three configurations — 268 core, 273 with the MCP
  extra, plus 8 differential — with `ruff`, `ruff format` and `mypy --strict`
  clean under each
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
- Every technical claim in `LAUNCH.md`

Not verified, because it cannot be from here:

- The PyPI upload. Blocked by egress policy.
- That anyone wants this. Nobody has used it yet. The market research went as far
  as testing every competing package; it did not extend to talking to a buyer,
  and it should before you build the next thing.
