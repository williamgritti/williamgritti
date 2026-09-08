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
  that silently corrupts rather than raising. Fourteen rules across Python,
  JavaScript/TypeScript, SQL, Java, PHP, Go, C# and Ruby, plus the schema formats
  that generate them (OpenAPI/JSON Schema, Protobuf, Prisma, GraphQL), each
  verified in the test suite to accept a legacy CNPJ and reject or corrupt an
  alphanumeric one.
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

### Reports written in Portuguese

The CLI addressed Brazilian developers in every string it printed except the
rule text, which was English, so a report read half-translated. Rule titles,
explanations and fixes are now Portuguese, and so is the remaining chrome.

`ValidationError.reason` is documented as a machine-readable code for caller-side
i18n; the CLI now uses it that way instead of printing the library's English
exception message. A test discovers the codes from the package source and fails
if one has no translation, so a new code cannot reach a user in English.

JSON and SARIF *keys* deliberately stay ASCII: they are the machine contract, and
only the human-readable values changed.

Long remediation text also wraps to a hanging indent instead of running past 140
columns, which is the part of a report a reader skips.

### The rule that check digits stay numeric was never tested

IN RFB 2.229/2024 widens the first twelve positions of a CNPJ and leaves the last
two numeric. That asymmetry is the defining detail of the format, and the reason
one ASCII-mapping code path can serve both formats at all.

`is_valid_cnpj` enforced it correctly, but nothing tested it: mutating that
guard's `return False` to `return True` left the whole suite green, so
`12ABC34501DEAB` would have validated and no test would have noticed. The
differential suite did not cover it either, because every case it generates
corrupts only the first twelve positions.

Found by mutation testing rather than by reading. `ACTIVATION.md` had claimed
this case was checked against the competing libraries, and it had been -- by
hand, earlier, and never turned into a test, which is exactly how a guard ends up
unprotected.

Both gaps are now closed, and the differential suite compares letters in the
check-digit positions against `brutils` and `validate-docbr` as well.

### A failed write left the tree half-fixed and raised a traceback

`apply_patches` wrote each file in turn with no error handling, so a write that
failed part-way through -- a read-only file, a full disk, a vanished directory --
raised out of the CLI as an unhandled `OSError`. Earlier files in the batch were
already rewritten, and the caller was left with a stack trace instead of the list
of what had changed, from a tool whose entire job is editing source files.

The read path had been careful about exactly this: unreadable files are counted
and skipped so one of them cannot abort a scan. The write path now matches. A
failure is collected rather than raised, `apply_patches` returns an `ApplyResult`
carrying both what was written and what was not, and the CLI prints each failure
to stderr.

The CLI also exits non-zero whenever a write failed, so a build gate never sees
success over a partly applied fix.

### `--fix` rewrote every line of a Windows-authored file

Applying a one-line fix to a file with CRLF endings converted the whole file to
LF. `git diff --numstat` reported every line changed instead of one.

`Path.read_text` opens in universal-newline mode, so CRLF came back as a bare LF
in the string, and writing that string out again normalised the file. The
emitted `--diff` had the same problem: its context lines carried normalised
endings, so the hunk covered the entire file.

This is the common case for the audience, not an exotic one. Brazilian
enterprise codebases are full of CRLF, and the whole point of emitting a patch
rather than a description is that a reviewer can see one line change. A patch
that rewrites the file is worse than no patch.

Reading and writing now preserve the separators verbatim, so a CRLF file stays
CRLF, an LF file stays LF, and a UTF-8 BOM survives. Verified byte for byte and
through `git apply`, which accepts the patch and leaves `numstat` at 1 line
added, 1 removed.

### The agent-facing scanner reported success for paths that do not exist

`escanear_projeto` answered `{"ok": true, ...}` with zero findings for any path
that was not there. An agent that mistyped a path, or passed one relative to the
wrong directory, was told the scan succeeded and the project was clean.

`scan_path` does not raise for a missing path -- `rglob` over a directory that is
not there simply yields nothing -- so the `except OSError` branch never fired for
the case it was written for. The CLI already exits 2 for both a missing path and
a scan that read nothing, with a comment giving the reason: silence from a tool
that looked at nothing must not read as a pass. The agent surface disagreed with
its own CLI.

The suite did not merely miss this. `test_scan_tools_are_exposed_to_agents`
asserted ``missing["ok"] is True``, pinning the defect down as correct behaviour.

Both a missing path and an empty scan now return `ok: false` with a reason, and
carry the same keys as a successful scan so a caller never branches on which
fields are present.

Found by launching the installed `fiscalkit-mcp` console script and speaking the
stdio protocol to it. The server had only ever been exercised through its tool
functions, which does not cover whether the process starts, negotiates, or lists
its tools -- all a client ever does.

### Scanning a single file told the user there was nothing to fix

`fiscalkit scan caminho/arquivo.py --fix` printed "nenhuma correção automática
disponível para os achados" and changed nothing. The same file scanned through
its directory was fixed correctly.

`Path.relative_to` returns "." when a path is compared with itself, so a
single-file scan reported every finding against ".". That reached further than
the report: the JSON `arquivo` field, the SARIF `artifactLocation.uri` that
GitHub anchors annotations on, and then `--fix`, where "." resolved back to the
containing directory, the read raised `IsADirectoryError`, and the patch builder
swallowed it along with genuinely unreadable files.

The result was a confident wrong answer with no error anywhere: exactly the
failure mode `CNPJ021` exists to catch in other people's code. The fallback
branch written for this case was unreachable, and its own comment said it
handled it.

Paths are now anchored on the parent when the target is a file, so a single-file
scan reads the same as that file found under a directory scan and the SARIF URI
stays relative. Covered by tests on both the reported path and on `--fix`
actually rewriting the file.

### The `Typing :: Typed` claim was not true

`pyproject.toml` declared the ``Typing :: Typed`` classifier and the README
showed a mypy-strict badge, but no PEP 561 ``py.typed`` marker was ever shipped.
PEP 561 says a package without that marker is to be treated as untyped however
well annotated it is, so none of the strict typing reached anyone installing it.

It was worse than losing the annotations. A consumer running mypy against the
built wheel got an error on the import itself:

    error: Skipping analyzing "fiscalkit": module is installed, but missing
    library stubs or py.typed marker  [import-untyped]

so the package broke their type check while advertising the opposite, and a real
argument-type error in the same file went unreported. With the marker in place
mypy reports that error correctly and clean code passes.

Found by inspecting the artifact `release.sh build` produces rather than trusting
the badge. Guarded at both levels, because they fail independently: a unit test
asserts the marker sits beside the installed package, and the build job asserts
it is present in the wheel and then type-checks a consumer against that wheel,
requiring the argument-type error to be reported and `import-untyped` not to be.

### `--diff` and `--fix`

Four rules -- the numeric regex, the non-digit strip, the numeric SQL column and
the ORM integer field -- have a rewrite that follows from the pattern alone, and
now carry it. `--diff` prints a unified diff in the shape `git apply` accepts,
verified with `git apply --check`; `--fix` applies it and reports what remains.

The ten rules without a rewrite are the point. `int(cnpj)` cannot be repaired by
editing that line, because the surrounding code has to stop treating a CNPJ as a
number; a tool that guessed would emit a plausible diff that silently changed
behaviour. Those stay reported and untouched.

Patches are built by re-reading each file rather than from the stored excerpt, so
they always apply to the file as it is now, and applying twice is a no-op. No
backup files are written: this is a source tree under version control.

### The context window was too tight for real code

Walking the first-user journey -- clean install, scan a realistic legacy Django
and Postgres project, apply each `correcao`, re-scan -- found the scanner missing
its own headline rule.

`CNPJ021`, the silent `re.sub(r"\D", "", ...)` corruption, went unreported in a
file that plainly contained it, because the helper was named `normalizar` and the
nearest mention of a CNPJ was four lines away, outside the two-line context
window. That is the ordinary layout of the code this tool targets.

The window is now 8, chosen by measurement rather than taste. Any value from 4
to 15 finds the helper and reports nothing across 3,225 third-party files, 41
files of the reference libraries and 240 files of Brazilian npm packages; cost
only appears beyond that, with two findings at 40. A test asserts the value stays
inside the range that was actually measured.

The journey now completes: six findings on the legacy project, zero after
applying each suggested fix, exit 0.

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

`CNPJ015` is scoped to Prisma, GraphQL and Go, the languages that write
`cnpj Int` with only whitespace between name and type. SQL is excluded because a
numeric column there belongs to `CNPJ011`, and matching both reported the same
line twice -- caught by the dogfood job, whose exact expected count made the
duplicate visible instead of letting it pass as a larger number.

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

The README claimed the ruleset covered eight languages, but the rules had only
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
