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
