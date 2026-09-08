"""Taxpayer identifier documents: CPF for natural persons, CNPJ for legal entities."""

from .cnpj import CNPJ, format_cnpj, is_alphanumeric_cnpj, is_valid_cnpj, strip_cnpj
from .cpf import CPF, format_cpf, is_valid_cpf, strip_cpf

__all__ = [
    "CNPJ",
    "CPF",
    "format_cnpj",
    "format_cpf",
    "is_alphanumeric_cnpj",
    "is_valid_cnpj",
    "is_valid_cpf",
    "strip_cnpj",
    "strip_cpf",
]
