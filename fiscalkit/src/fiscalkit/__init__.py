"""fiscalkit -- Brazilian fiscal documents for Python and AI agents.

Validate CPF and CNPJ (including the alphanumeric CNPJ mandatory from July 2026),
decode NF-e access keys without a SEFAZ round trip, and parse NF-e XML into typed
objects with :class:`~decimal.Decimal` money.

Basic use::

    from fiscalkit import AccessKey, CNPJ, parse_nfe_file

    key = AccessKey.parse("35200114200166000187550010000000015110000001")
    print(key.uf.name, key.emitted_on, key.model_name)

    CNPJ.parse("11.222.333/0001-81").is_matriz  # True

    nfe = parse_nfe_file("nota.xml")
    print(nfe.issuer.name, nfe.totals.invoice_total, nfe.totals_reconcile())
"""

from __future__ import annotations

from .codes.cfop import CFOPInfo, classify_cfop, is_valid_cfop
from .codes.uf import UF, UFS, by_acronym, by_code, is_valid_uf_code
from .documents.cnpj import (
    CNPJ,
    format_cnpj,
    is_alphanumeric_cnpj,
    is_valid_cnpj,
    strip_cnpj,
)
from .documents.cpf import CPF, format_cpf, is_valid_cpf, strip_cpf
from .exceptions import (
    FiscalKitError,
    ParseError,
    UnsupportedDocumentError,
    ValidationError,
)
from .nfe.chave import (
    AccessKey,
    access_key_check_digit,
    format_access_key,
    is_valid_access_key,
)
from .nfe.models import Address, Item, NFe, Party, Product, Totals
from .nfe.parser import parse_nfe, parse_nfe_file

__version__ = "0.1.0"

__all__ = [
    "CNPJ",
    "CPF",
    "UF",
    "UFS",
    "AccessKey",
    "Address",
    "CFOPInfo",
    "FiscalKitError",
    "Item",
    "NFe",
    "ParseError",
    "Party",
    "Product",
    "Totals",
    "UnsupportedDocumentError",
    "ValidationError",
    "# access key",
    "# codes",
    "# documents",
    "# exceptions",
    "# nfe",
    "__version__",
    "access_key_check_digit",
    "by_acronym",
    "by_code",
    "classify_cfop",
    "format_access_key",
    "format_cnpj",
    "format_cpf",
    "is_alphanumeric_cnpj",
    "is_valid_access_key",
    "is_valid_cfop",
    "is_valid_cnpj",
    "is_valid_cpf",
    "is_valid_uf_code",
    "parse_nfe",
    "parse_nfe_file",
    "strip_cnpj",
    "strip_cpf",
]
