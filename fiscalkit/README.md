# fiscalkit

**Brazilian fiscal documents for Python and AI agents.**

[![CI](https://github.com/williamgritti/fiscalkit/actions/workflows/ci.yml/badge.svg)](https://github.com/williamgritti/fiscalkit/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/fiscalkit/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Typed](https://img.shields.io/badge/mypy-strict-brightgreen)](pyproject.toml)

Validate CPF and CNPJ, decode NF-e access keys without calling SEFAZ, and parse
NF-e XML into typed objects with `Decimal` money. Zero runtime dependencies.
Ships with a CLI and an MCP server, so the same logic serves your code, your
terminal, and your AI agent.

> **`fiscalkit scan` finds the code in your project that breaks in July 2026.**
> Validation libraries already handle the alphanumeric CNPJ. Your `^\d{14}$`
> regex, your `BIGINT` column and your `int(cnpj)` cast do not — and no
> dependency upgrade fixes those. Nothing else scans for them.

```bash
pip install fiscalkit
```

---

## Why this exists

Brazilian fiscal data is unusually hostile to work with. Access keys are packed
44-digit records that most code treats as opaque strings. NF-e XML arrives in at
least three different root shapes, is frequently ISO-8859-1, and buries the same
tax value under a dozen CST-specific element names.

The Brazilian Python ecosystem already covers parts of this well, and `fiscalkit`
does not pretend otherwise — the comparison below is honest about what is already
solved elsewhere. What this package offers is the combination in one
zero-dependency, strictly-typed place: identifier validation, access-key decoding,
XML parsing, a CLI and an MCP server behind a single small API.

If you only need CPF/CNPJ validation, use `brutils` — it is excellent and far
broader. Reach for `fiscalkit` when you also want the access key decoded and the
XML parsed without pulling in a code-generated schema stack.

---

## The 2026 problem nobody is scanning for

From July 2026, *IN RFB nº 2.229/2024* allows letters in the first twelve
positions of a CNPJ. Every serious validation library already handles this —
`brutils`, `validate-docbr` and `fiscalkit` all agree on every edge case.

**That is not where systems break.** They break in the code *around* the
validator, none of which a dependency upgrade touches:

```console
$ fiscalkit scan .
QUEBRA app/fornecedor.py:3  [CNPJ001] Numeric-only CNPJ regex
       CNPJ_RE = re.compile(r"^\d{14}$")
       correcao: Match [0-9A-Z]{12}[0-9]{2} instead: the first twelve positions
                 accept letters, the two check digits stay numeric.

QUEBRA app/fornecedor.py:8  [CNPJ012] CNPJ mapped to an integer field in an ORM
       cnpj = models.BigIntegerField(unique=True)
       correcao: Use a character field of length 14.

QUEBRA schema.sql:3  [CNPJ011] CNPJ column declared as a numeric type
       cnpj BIGINT NOT NULL UNIQUE,
       correcao: Migrate to CHAR(14) or VARCHAR(14). Plan for a backfill and for
                 every foreign key that references this column.

2 arquivo(s) analisado(s), 6 ocorrencia(s): 6 quebra, 0 risco, 0 rever
```

Each pattern is verified in the test suite to accept `11222333000181` and reject
or corrupt `12ABC34501DE35`. A rule that cannot demonstrate that difference is not
shipped as a rule.

The insidious one is `re.sub(r"\D", "", cnpj)`: it raises nothing, it just
silently returns a shorter, wrong value that then fails validation somewhere else
entirely.

`scan` exits non-zero **only** on certain breakage, so it gates a build without
failing it on advisory findings:

```bash
fiscalkit scan . --json | jq '.pronto_para_2026'
```

Twelve rules across Python, JavaScript/TypeScript, SQL, Java, PHP, Go, C# and
Ruby. Dependency directories are pruned and commented-out code is ignored,
because a scanner that cries wolf gets muted after one run.

---

## Quick start

### Decode an access key

Everything below is computed locally. No network, no SEFAZ certificate.

```python
from fiscalkit import AccessKey

key = AccessKey.parse("4324 0311 2223 3300 0181 5500 1000 0001 2310 0000 0010")

key.uf.name          # 'Rio Grande do Sul'
key.emitted_on       # datetime.date(2024, 3, 1)
key.cnpj             # '11222333000181'
key.model_name       # 'NF-e (Nota Fiscal Eletrônica)'
key.number           # '000000123'
key.is_contingency   # False
```

### Validate a CNPJ, old format or new

One code path serves both. The 2026 algorithm maps each character with
`ord(c) - 48`, which reproduces the legacy numeric result exactly — so you need
no feature flag and no migration date.

```python
from fiscalkit import CNPJ, is_valid_cnpj

is_valid_cnpj("11.222.333/0001-81")   # True  (legacy numeric)
is_valid_cnpj("12.ABC.345/01DE-35")   # True  (alphanumeric, 2026)

cnpj = CNPJ.parse("11.222.333/0001-81")
cnpj.raiz              # '11222333'  -- shared by every branch
cnpj.is_matriz         # True
cnpj.is_alphanumeric   # False
```

### Parse an NF-e

```python
from fiscalkit import parse_nfe_file

nfe = parse_nfe_file("nota.xml")

nfe.issuer.name              # 'Comercio Exemplo Ltda'
nfe.totals.invoice_total     # Decimal('233.90')
nfe.is_authorized            # True
nfe.totals_reconcile()       # True -- line items sum to the declared total
```

`totals_reconcile()` is the check worth wiring into an ingestion pipeline: it
re-adds the line items and compares against the document's own declared total.
A mismatch means the file is malformed or was edited after signing.

### From the terminal

```console
$ fiscalkit chave 43240311222333000181550010000001231000000010
chave      4324 0311 2223 3300 0181 5500 1000 0001 2310 0000 0010
uf         RS (Rio Grande do Sul)
emissao    2403  (2024-03-01)
cnpj       11222333000181
modelo     55 - NF-e (Nota Fiscal Eletrônica)
serie      001
numero     000000123
emissao    Normal

$ fiscalkit cnpj 12ABC34501DE35
12.ABC.345/01DE-35  valido  (alfanumerico, filial 01DE)
```

Every command takes `--json` and exits non-zero on invalid input, so it drops
straight into a shell pipeline or a CI gate:

```bash
fiscalkit nfe nota.xml --json | jq '.totais_conferem'
```

---

## Use it from an AI agent

`fiscalkit` ships an MCP server. Point Claude Code, Claude Desktop, or any MCP
client at it and the model can read fiscal documents directly.

```bash
pip install 'fiscalkit[mcp]'
```

```json
{
  "mcpServers": {
    "fiscalkit": { "command": "fiscalkit-mcp" }
  }
}
```

Ten tools are exposed: `validar_cpf`, `validar_cnpj`, `calcular_dv_cnpj`,
`decodificar_chave`, `analisar_nfe`, `escanear_codigo`, `escanear_projeto`,
`classificar_cfop`, `consultar_uf` and `listar_ufs`.

`escanear_codigo` lets an agent check a snippet it is about to write or review
for 2026 breakage, which is where the mistake is cheapest to catch.

Works with both `mcp` 1.x and 2.x — the SDK renamed `FastMCP` to `MCPServer` in
2.0, and `fiscalkit` detects which one you have rather than making you pin.

`fiscalkit` is not the only Brazilian fiscal MCP server: [`fiscal-mcp`](https://pypi.org/project/fiscal-mcp/)
validates NF-e, NFC-e and NFS-e against the official XSD schemas and covers
IBS/CBS. If you need schema-level validation or NFS-e, use that one — it goes
deeper on validation than this does.

Invalid input comes back as a payload with `"valido": false` and a reason code,
never as an exception. An agent that receives a structured "no" explains the
problem; an agent that receives a stack trace just retries.

---

## One thing worth knowing about check digits

The NF-e access key's check digit is a **transcription guard, not a tamper seal.**

The spec maps mod-11 remainders 0 *and* 1 onto the same check digit of 0. So for
the roughly two keys in eleven that end in 0, a number of single-digit changes
still validate. Keys ending in any other digit do catch every single-digit
substitution.

This library documents that rather than papering over it, and the property is
[pinned by a test](tests/test_chave.py). If you need authenticity rather than
typo-detection, you need the issuer's digital signature or a SEFAZ query — not
the check digit.

---

## How this compares

The Brazilian fiscal ecosystem is not empty. Here is where each package actually
sits, verified by installing and testing them rather than by reading summaries:

| Package | What it does | Overlap |
|---|---|---|
| [`brutils`](https://pypi.org/project/brutils/) | Broad Brazilian utilities: CPF, CNPJ, CEP, phone, plates, legal process. **Alphanumeric CNPJ handled correctly.** | Supersedes `fiscalkit` for identifier validation. Has **no** access-key decoding. |
| [`validate-docbr`](https://pypi.org/project/validate-docbr/) | Document validation. Alphanumeric CNPJ handled correctly. | Same — identifiers only. |
| [`nfelib`](https://pypi.org/project/nfelib/) | XSD-generated NF-e bindings, full layout coverage. | Far more complete for XML; heavier, code-generated. |
| [`PyNFe`](https://pypi.org/project/PyNFe/) | SEFAZ web-service transport, certificate handling, transmission. | Different problem — `fiscalkit` never touches the network. |
| [`fiscal-mcp`](https://pypi.org/project/fiscal-mcp/) | Offline NF-e/NFC-e/NFS-e validation against official XSD, IBS/CBS, as an MCP server. | Directly overlapping and deeper on validation. Use it if you need XSD or NFS-e. |

**Where `fiscalkit` is actually worth choosing:** `fiscalkit scan` has no
equivalent anywhere — every package above validates a CNPJ, none of them finds the
code that will reject one. Beyond that: access-key decoding, NF-e parsing and
identifier validation in one dependency-free package with `Decimal` money,
`mypy --strict` types, a CLI that exits non-zero for CI, and an MCP server —
without a code-generated schema layer. Access-key decoding in
particular is missing from the general-purpose libraries.

If that is not what you need, one of the packages above probably fits better.
That is a genuine recommendation, not false modesty.

---

## What's covered

| | |
|---|---|
| **CPF** | validation, formatting, repeated-digit rejection |
| **CNPJ** | numeric **and** alphanumeric (2026), root/branch, check-digit generation |
| **Access key** | full 44-digit decode, validation, DANFE-style formatting |
| **NF-e XML** | `nfeProc` / `NFe` / `infNFe` roots, items, taxes across CST variants, totals, protocol |
| **2026 scanner** | 12 rules over 8 languages finding code that breaks on alphanumeric CNPJs |
| **CFOP** | direction and scope classification |
| **UF** | all 27 IBGE codes, lookup by code or acronym |

Money is `Decimal` throughout. Binary floats silently corrupt totals that tax
authorities reconcile to the cent.

## Roadmap

- CT-e and MDF-e parsing (the access key decoder already handles their models)
- NFS-e, once the national standard settles
- Inscrição Estadual validation, per-state
- SPED Fiscal block parsing

Issues and PRs welcome. If you hit an NF-e this fails to parse, open an issue
with the smallest XML that reproduces it — with real identifiers redacted.

## Development

```bash
git clone https://github.com/williamgritti/fiscalkit
cd fiscalkit
pip install -e '.[dev,mcp]'

pytest              # 181 tests
ruff check src tests
mypy src/fiscalkit  # strict
```

## License

MIT — see [LICENSE](LICENSE).

---

<sub>Built by [William Gritti](https://github.com/williamgritti) — IT analyst,
Python developer, and tax-law specialist. Fifteen years inside the Brazilian
public sector, which is where the motivation for this came from.</sub>
