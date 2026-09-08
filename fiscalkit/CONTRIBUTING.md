# Contributing

Thanks for considering a contribution.

## Reporting a parsing failure

The most useful issue you can open is an NF-e this library fails to parse.
Please include the smallest XML that reproduces it, **with real identifiers
redacted** — replace CNPJ, CPF, names and addresses with the kind of placeholder
values used in `tests/test_parser.py`. Never paste a real fiscal document into a
public issue.

## Development

```bash
pip install -e '.[dev,mcp]'
pytest
ruff check src tests
ruff format --check src tests
mypy src/fiscalkit
```

All four must pass; CI runs exactly these on Python 3.10 through 3.13.

## Conventions

- Money is `Decimal`, never `float`.
- Validators return `bool`; parsers raise `ValidationError` with a machine-readable
  `reason`. Keep both surfaces available for new document types.
- MCP tools return a payload describing failure rather than raising, so an agent
  gets a structured answer it can explain.
- Comment the *why*, especially where a rule comes from legislation. A citation to
  the instrução normativa or the technical manual is worth more than a paraphrase.
