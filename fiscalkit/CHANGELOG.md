# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-08

First release.

### Added

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
