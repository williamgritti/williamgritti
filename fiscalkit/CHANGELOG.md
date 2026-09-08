# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-08

First release.

### Added

- **`fiscalkit scan`** -- static analysis for the July 2026 alphanumeric CNPJ
  transition, and the one capability with no equivalent elsewhere. Validation
  libraries already handle the new format; what breaks is the surrounding code,
  which no dependency upgrade touches: `^\d{14}$` regexes, `BIGINT` columns,
  ORM integer fields, `int(cnpj)` casts, and `re.sub(r"\D", ...)` normalization
  that silently corrupts rather than raising. Twelve rules across Python,
  JavaScript/TypeScript, SQL, Java, PHP, Go, C# and Ruby, each verified in the
  test suite to accept a legacy CNPJ and reject or corrupt an alphanumeric one.
  Exits non-zero only on certain breakage so it can gate a build, and is exposed
  to agents as the `escanear_codigo` and `escanear_projeto` MCP tools.
- **SARIF 2.1.0 output** (`--format sarif`) for GitHub code scanning, so findings
  are annotated on the pull request line and listed in the Security tab rather
  than buried in a log. Generation always exits 0, because an upload step needs
  its file even when the scan itself fails the job.
- **A composite GitHub Action** (`action.yml`) and a **pre-commit hook**
  (`.pre-commit-hooks.yaml`), so the check runs on every pull request in three
  lines of configuration.

- **CPF** validation, formatting and repeated-digit rejection.
- **CNPJ** validation supporting both the legacy numeric format and the
  alphanumeric format from *IN RFB nº 2.229/2024*, mandatory from July 2026.
  A single `ord(c) - 48` mapping serves both, so no feature flag is needed.
  Includes check-digit generation via `check_digits_for`. Note that `brutils` and
  `validate-docbr` already implement the alphanumeric rules correctly; this is
  parity, not a differentiator.
- **Access key** decoding: full 44-digit breakdown into state, emission period,
  issuer CNPJ, model, series, number, emission type and check digit.
- **NF-e XML parsing** for `nfeProc`, `NFe` and bare `infNFe` roots, matching
  elements by local name so namespace-stripped files still parse. Handles
  ISO-8859-1 payloads and sums taxes across CST-specific element variants.
- `NFe.totals_reconcile()`, which re-adds line items and compares against the
  document's declared total.
- **CFOP** direction and scope classification; **UF** lookup for all 27 IBGE codes.
- **CLI** (`fiscalkit`) with `--json` output and non-zero exit codes on invalid
  input, usable as a CI gate.
- **MCP server** (`fiscalkit-mcp`) exposing eight tools to AI agents, returning
  structured failure payloads rather than raising.

### Pruning and bundled output are reported, never silent

Scanning three real Brazilian npm packages showed one file analysed each, out of
240. A published npm package keeps its only copy of the code in `dist`, which is
pruned as build output -- correct for a source repository, wrong for a published
artifact, and in both cases it reported the package ready without reading a line
of it. The same false all-clear as the `site-packages` bug, by another route.

- `ScanResult` now counts what pruning hid, per directory, and the CLI warns.
  `--incluir-tudo` (`prune=False`) turns pruning off for published artifacts.
- Minified and bundled files are set aside and counted rather than reported.
  A finding on line 1 of a one-line bundle is unactionable: the excerpt is a
  slice of an enormous line and the fix belongs in source that lives elsewhere.

That scan also corrected, then re-corrected, a claim in this project's own
documentation. All five validation libraries tested by execution support the
alphanumeric CNPJ: `brutils` and `validate-docbr` in Python;
`cpf-cnpj-validator`, `validation-br` and `@brazilian-utils/brazilian-utils` in
JavaScript. The last gates it behind `{ version: 2 }` and defaults to
numeric-only for backwards compatibility, so its default rejects an alphanumeric
CNPJ while the library validates one correctly, negative cases included, once
the option is passed.

An intermediate version of this changelog reported that library as not
2026-ready, having tested only its default. That was wrong and unfair to its
maintainers, and it is recorded here rather than quietly rewritten, because it
is the same over-generalisation this project has now made four times: test a
sample, state a universal.

### Schema and interface-definition formats

Testing the formats a Brazilian system actually carries found three gaps. An
OpenAPI spec declaring `cnpj` with `type: integer` produced nothing, because the
type sits on its own line under the field name and no single-line rule could see
both. `.proto`, `.prisma` and `.graphql` were not recognised at all, so
`int64 cnpj = 1;` was never read.

These matter more than an equivalent line of application code: a CNPJ typed as
an integer in a specification propagates into every generated client, server
stub and validator, so one line becomes the same defect in several languages.

Added `CNPJ014` for the type-on-its-own-line case, context-gated, and `CNPJ015`
for `cnpj Int` with only whitespace between name and type, which Prisma and IDLs
use. `.proto`, `.prisma`, `.graphql`, `.gql` and `.avsc` are now read.

`CNPJ015` first matched `print("cnpj integer")`, since prose puts the same two
words together. It now requires the shape of a declaration -- end of line, an
attribute, or punctuation after the type, never a closing quote. Re-measured
after the change: zero false positives across 3,234 third-party files and 240
files of Brazilian npm packages.

### The coercion rule now distinguishes NaN from silent truncation

`CNPJ004` matches `Number`, `isNaN`, `ctype_digit`, `parseFloat` and `parseInt`,
and told the reader that numeric coercion "yields NaN or false". Running each one
shows that holds for every spelling except the most common:
`parseInt("12ABC34501DE35", 10)` returns **12**, with no error and no NaN.

That is the dangerous case and the old text denied it. A reader using `parseInt`
was being told to expect a failure they will never see, while a plausible
two-digit number reaches their database. The explanation now separates the loud
failures from the silent one and quotes the truncated value.

### The numeric-column rule now describes what databases actually do

`CNPJ011` said an integer column "cannot store" an alphanumeric CNPJ. Running it
shows that is true of PostgreSQL, MySQL and SQLite STRICT tables, and false of
SQLite's default type affinity, which accepts the value and stores it as TEXT in
a column declared `BIGINT`.

That case is the more dangerous one. Legacy rows stay integers, new ones become
text, and nothing fails until a join, an `ORDER BY` or a comparison touches the
column. A reader on SQLite told only "cannot store" would reasonably conclude
they are unaffected. The rule text now covers both outcomes and a test executes
each against a real database rather than asserting them.

### Differential tests against independent implementations

Every correctness test in this package was written by the same author as the
code it checks, so a misreading of the specification would be reproduced
faithfully on both sides and pass. The claim that `fiscalkit` "agrees with
`brutils` on every edge case" rested on five hand-picked examples.

Replaced with a differential suite comparing against `brutils` and
`validate-docbr`, two implementations written by other people from the same
published rules. Across 60,000 generated cases -- numeric CNPJ, alphanumeric
CNPJ and CPF, half valid and half corrupted in a random position -- there were
**zero disagreements** with either reference. Check digits generated by
`check_digits_for` are also fed back to both references, which catches a
generator that agrees with our own validator because both share a mistake.

Skipped when the references are absent; a CI job installs them and runs it.

### Verified the remaining documented claims

- **`mcp` 1.x support was claimed but never executed.** The optional extra
  resolves to 2.x, so the 1.x half of the import fallback had never run
  anywhere. Installed `mcp<2` (1.30.0) and confirmed `_server_class()` resolves
  to `FastMCP`, ten tools register, `call_tool` round-trips, and the full suite
  and `mypy --strict` pass. CI now has a job that pins the 1.x SDK, so the claim
  stays true rather than being true by accident.
- **The pre-commit hook had never been run through pre-commit.** Validated the
  manifest against pre-commit's own schema and executed the hook in a real git
  repository: it fails with a readable diagnostic on a project with breakage and
  passes on a clean one. Both manifests are now covered by tests, including that
  the Action's scan steps tolerate a non-zero exit, which is the bug that would
  otherwise return the moment anyone edits that file.

### Made the multi-language claim true

The README claimed twelve rules across eight languages, but the rules had only
ever been tested against Python and SQL. Checked against idiomatic CNPJ handling
in each claimed language and **eight of twenty-one cases were missed**: Go's
`strconv.Atoi`, C#'s `Int32.Parse` and `public long Cnpj { get; set; }`, Ruby's
`row[:cnpj].to_i`, PHP's `intval` and argument-position `str_pad`, Java's
type-first `private BigInteger cnpj;`, and a chained `String(x.cnpj).padStart`.

The rules were written Python-first and assumed the CNPJ is always the receiver
of a method and always named before its type. Widened to cover argument
position, method chains and type-first declarations; all twenty-one now fire.
Precision was re-measured afterwards rather than assumed: twelve adversarial
probes clean, and 3,212 third-party files plus 41 of `brutils` and
`validate-docbr` still report nothing.

A documented claim the code does not honour is the same defect as a false one.

### Validated against real Brazilian CNPJ code

Running the scanner against `brutils` 2.5.0 and `validate-docbr` 2.0.0 -- 41
files of production Brazilian fiscal code that is already 2026-ready -- plus
3,212 files of unrelated third-party code, produced **zero false positives**,
and surfaced one serious defect:

- `site-packages` and other pruned directory names were matched against every
  component of the absolute path, including the root the caller named. Pointing
  the scanner at a directory inside one of them skipped every file and reported
  the project ready. A false all-clear is the worst answer a compliance tool can
  give, so pruning now applies only below the given root.
- A scan that examined no files no longer counts as clean. `is_clean` requires
  at least one file scanned, `scanned_nothing` reports the case, and the CLI
  exits 2 rather than 0, because silence from a tool that looked at nothing must
  not read as a pass.

Probing the one rule that was neither context-gated nor keyed on the word
"cnpj" found four false positives its pattern would have produced on ordinary
code: version strings, dotted dates, coordinates, and the Brazilian CEP mask
`\d{2}\.\d{3}-\d{3}` -- which appears in every address form in the country,
so it would have fired in precisely the codebases this tool targets. The rule is
now anchored on the `/0000` branch group unique to a CNPJ mask, and gated on
nearby context like the others.

The precision the scanner claims is now demonstrated rather than asserted:
`brutils` writes `cnpj[12:].isdigit()`, which is exactly right under the new
rules since only the two check digits stay numeric, and the scanner leaves it
alone while still catching the unsliced `cnpj.isdigit()`. Both are pinned by
tests.

### Hardened against hostile input

Found by an adversarial audit before release, each pinned by a regression test:

- `Decimal` accepts `"NaN"`, `"sNaN"` and `"Infinity"` without complaint, so such
  a value from third-party XML parsed cleanly and only detonated later during
  arithmetic, as an uncaught `decimal.InvalidOperation` escaping the library's
  error hierarchy. Non-finite and absurd-magnitude amounts are now refused at
  parse time and degrade to zero like any other unreadable field.
- The `AAMM` slice of an access key was never range-checked, so a key with month
  `00` or `13` passed `is_valid_access_key`, then raised a bare `ValueError` from
  `datetime` out of `emitted_on` — crashing `to_dict()`, the `decodificar_chave`
  MCP tool, and the CLI with a traceback. The month is now validated at parse
  time, and `emitted_on` raises `ValidationError` if reached another way.
- The CLI decoded NF-e files as UTF-8 with `errors="replace"`, corrupting the
  ISO-8859-1 documents the library itself reads correctly. It now passes raw
  bytes so the XML declaration decides the encoding.
- `calcular_dv_cnpj` normalized with `str.isalnum()`, which is true for non-ASCII
  letters such as `Ç`, and could return a 15-character value that was not a CNPJ.
  It now uses `strip_cnpj`.
- Five section comments had been swept into the top-level `__all__`, so
  `from fiscalkit import *` raised `AttributeError`.

### Notes

- Money is `Decimal` throughout; binary floats corrupt cent-level reconciliation.
- The access key check digit is documented as a transcription guard rather than a
  tamper seal: the spec collapses mod-11 remainders 0 and 1 onto the same check
  digit, so some single-digit changes survive on keys ending in 0. This behaviour
  is pinned by tests.

[0.1.0]: https://github.com/williamgritti/fiscalkit/releases/tag/v0.1.0
