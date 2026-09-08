# fiscalkit

**Brazilian fiscal documents for Python and AI agents.**

[![CI](https://github.com/williamgritti/fiscalkit/actions/workflows/ci.yml/badge.svg)](https://github.com/williamgritti/fiscalkit/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/fiscalkit/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/williamgritti/fiscalkit/blob/main/LICENSE)
[![Typed](https://img.shields.io/badge/mypy-strict-brightgreen)](https://github.com/williamgritti/fiscalkit/blob/main/pyproject.toml)

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
positions of a CNPJ. Validation libraries already handle it — all five tested by
execution agree with `fiscalkit` on every edge case: `brutils`,
`validate-docbr`, `cpf-cnpj-validator`, `validation-br`, and
`@brazilian-utils/brazilian-utils`, the last requiring `{ version: 2 }` since its
default stays numeric for backwards compatibility.

**That is not where systems break.** They break in the code *around* the
validator, none of which a dependency upgrade touches:

```console
$ fiscalkit scan .
QUEBRA app/fornecedor.py:4  [CNPJ001] Regex de CNPJ que aceita apenas dígitos
       CNPJ_RE = re.compile(r"^\d{14}$")
       correção: Use [0-9A-Z]{12}[0-9]{2}: as doze primeiras posições aceitam letras e os
                 dois dígitos verificadores continuam numéricos.

QUEBRA app/fornecedor.py:8  [CNPJ012] CNPJ mapeado como campo inteiro no ORM
       cnpj = models.BigIntegerField(unique=True)
       correção: Use um campo de caractere com tamanho 14.

QUEBRA schema.sql:3  [CNPJ011] Coluna de CNPJ declarada com tipo numérico
       cnpj BIGINT NOT NULL UNIQUE
       correção: Migre para CHAR(14) ou VARCHAR(14). Planeje o backfill e todas as chaves
                 estrangeiras que referenciam esta coluna.

2 arquivo(s) analisado(s), 3 ocorrência(s): 3 quebra, 0 risco, 0 rever
```

The report is written in Portuguese, because the people who have to act on it
are. The JSON and SARIF keys stay ASCII, so the machine-readable contract is
unaffected.

Each pattern is verified in the test suite to accept `11222333000181` and reject
or corrupt `12ABC34501DE35`. A rule that cannot demonstrate that difference is not
shipped as a rule.

The insidious one is `re.sub(r"\D", "", cnpj)`: it raises nothing, it just
silently returns a shorter, wrong value that then fails validation somewhere else
entirely.

### It writes the patch, for the fixes that are unambiguous

Reporting a problem leaves the work with you. Against a fixed deadline that is
not much help, so four of the fourteen rules carry the rewrite with them:

```console
$ fiscalkit scan . --diff
--- a/app/validators.py
+++ b/app/validators.py
@@ -1,10 +1,10 @@
-CNPJ_RE = re.compile(r"^\d{14}$")
+CNPJ_RE = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")
 def normalizar(valor):
-    return re.sub(r"\D", "", valor)
+    return re.sub(r"[^0-9A-Z]", "", valor)
```

The output is in the shape `git apply` accepts, so you can review it as a patch
before touching anything. `--fix` applies it and reports what is left.

**What it will not fix matters more than what it will.** `int(cnpj)` has no
mechanical repair: the surrounding code has to stop treating a CNPJ as a number,
and a tool that guessed would emit a plausible diff that silently changed
behaviour. Those findings stay reported and untouched, and `--fix` says how many
remain for a human.

`scan` exits non-zero **only** on certain breakage, so it gates a build without
failing it on advisory findings:

```bash
fiscalkit scan . --json | jq '.pronto_para_2026'
```

Write reports outside the tree you are scanning. A `.json` report left inside it
is scanned on the next pass — the rule explanations contain the very patterns the
rules look for — and `--fix` will rewrite the report rather than your code.

### In CI, with findings annotated on the pull request

`--format sarif` emits SARIF 2.1.0, which GitHub code scanning ingests — so
findings land on the exact line of the diff and in the Security tab, instead of
buried in a log:

```yaml
- uses: williamgritti/fiscalkit@main
  id: cnpj
- uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: fiscalkit.sarif
```

The action writes a job summary, exposes `total`, `breaking` and `ready` as
outputs, and fails the job only on certain breakage (`fail-on-break: false` to
report without failing). SARIF generation always exits 0 so the upload succeeds
even on a failing scan.

`sarif-file` resolves against the **workspace root**, not against any
`working-directory` your workflow sets — composite action steps do not inherit
that default. The action logs the absolute path it wrote.

### As a pre-commit hook

```yaml
repos:
  - repo: https://github.com/williamgritti/fiscalkit
    rev: v0.1.0
    hooks:
      - id: cnpj-2026
```

14 rules across Python, JavaScript/TypeScript, SQL, Java, PHP, Go, C#, Ruby,
plus the schema formats that generate them: OpenAPI/JSON Schema, Protobuf,
Prisma and GraphQL. Dependency directories are pruned and commented-out code is ignored,
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
emissão    2403  (2024-03-01)
cnpj       11222333000181
modelo     55 - NF-e (Nota Fiscal Eletrônica)
série      001
número     000000123
emissão    Normal

$ fiscalkit cnpj 12ABC34501DE35
12.ABC.345/01DE-35  válido  (alfanumérico, filial 01DE)
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
[pinned by a test](https://github.com/williamgritti/fiscalkit/blob/main/tests/test_chave.py). If you need authenticity rather than
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
| **2026 scanner** | 14 rules over 8 languages plus OpenAPI, Protobuf, Prisma and GraphQL |
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

## Rodou o scanner e apareceu coisa demais?

Se `fiscalkit scan` encontrou dezenas de ocorrências no seu sistema, a parte
difícil não é a regex: é a coluna do banco, o backfill e as chaves estrangeiras
que apontam pra ela. Isso precisa começar bem antes de junho de 2026.

Abra uma [issue](https://github.com/williamgritti/fiscalkit/issues) ou uma
[discussion](https://github.com/williamgritti/fiscalkit/discussions) descrevendo
o tamanho do estrago — quantas ocorrências, em quantos repositórios, e se o CNPJ
está em coluna numérica. Dá pra responder o que é urgente e o que pode esperar.

Para conversar em particular sobre migração, o contato está no perfil:
[@williamgritti](https://github.com/williamgritti).

## Development

```bash
git clone https://github.com/williamgritti/fiscalkit
cd fiscalkit
pip install -e '.[dev,mcp]'

pytest              # totals vary by extra; the suite prints its own
ruff check src tests
mypy src/fiscalkit  # strict
```

## License

MIT — see [LICENSE](https://github.com/williamgritti/fiscalkit/blob/main/LICENSE).

---

<sub>Built by [William Gritti](https://github.com/williamgritti) — IT analyst,
Python developer, and tax-law specialist. Fifteen years inside the Brazilian
public sector, which is where the motivation for this came from.</sub>
