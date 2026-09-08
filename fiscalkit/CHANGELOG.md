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
  Includes check-digit generation via `check_digits_for`.
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

### Notes

- Money is `Decimal` throughout; binary floats corrupt cent-level reconciliation.
- The access key check digit is documented as a transcription guard rather than a
  tamper seal: the spec collapses mod-11 remainders 0 and 1 onto the same check
  digit, so some single-digit changes survive on keys ending in 0. This behaviour
  is pinned by tests.

[0.1.0]: https://github.com/williamgritti/fiscalkit/releases/tag/v0.1.0
