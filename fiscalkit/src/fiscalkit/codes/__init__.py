"""Lookup tables for the coded fields that appear inside fiscal documents."""

from .cfop import CFOPInfo, classify_cfop, is_valid_cfop, strip_cfop
from .uf import UF, UFS, by_acronym, by_code, is_valid_uf_code

__all__ = [
    "UF",
    "UFS",
    "CFOPInfo",
    "by_acronym",
    "by_code",
    "classify_cfop",
    "is_valid_cfop",
    "is_valid_uf_code",
    "strip_cfop",
]
