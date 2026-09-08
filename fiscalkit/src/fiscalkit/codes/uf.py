"""IBGE state codes (``cUF``) used throughout Brazilian fiscal documents.

The two-digit ``cUF`` prefixes every NF-e access key and appears in the ``ide``
block of the document itself. The first digit encodes the macro-region, which is
why the codes are not contiguous.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["UF", "UFS", "by_acronym", "by_code", "is_valid_uf_code"]


@dataclass(frozen=True, slots=True)
class UF:
    """A Brazilian federative unit."""

    code: int
    acronym: str
    name: str
    region: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.acronym


UFS: tuple[UF, ...] = (
    UF(11, "RO", "Rondônia", "Norte"),
    UF(12, "AC", "Acre", "Norte"),
    UF(13, "AM", "Amazonas", "Norte"),
    UF(14, "RR", "Roraima", "Norte"),
    UF(15, "PA", "Pará", "Norte"),
    UF(16, "AP", "Amapá", "Norte"),
    UF(17, "TO", "Tocantins", "Norte"),
    UF(21, "MA", "Maranhão", "Nordeste"),
    UF(22, "PI", "Piauí", "Nordeste"),
    UF(23, "CE", "Ceará", "Nordeste"),
    UF(24, "RN", "Rio Grande do Norte", "Nordeste"),
    UF(25, "PB", "Paraíba", "Nordeste"),
    UF(26, "PE", "Pernambuco", "Nordeste"),
    UF(27, "AL", "Alagoas", "Nordeste"),
    UF(28, "SE", "Sergipe", "Nordeste"),
    UF(29, "BA", "Bahia", "Nordeste"),
    UF(31, "MG", "Minas Gerais", "Sudeste"),
    UF(32, "ES", "Espírito Santo", "Sudeste"),
    UF(33, "RJ", "Rio de Janeiro", "Sudeste"),
    UF(35, "SP", "São Paulo", "Sudeste"),
    UF(41, "PR", "Paraná", "Sul"),
    UF(42, "SC", "Santa Catarina", "Sul"),
    UF(43, "RS", "Rio Grande do Sul", "Sul"),
    UF(50, "MS", "Mato Grosso do Sul", "Centro-Oeste"),
    UF(51, "MT", "Mato Grosso", "Centro-Oeste"),
    UF(52, "GO", "Goiás", "Centro-Oeste"),
    UF(53, "DF", "Distrito Federal", "Centro-Oeste"),
)

_BY_CODE = {uf.code: uf for uf in UFS}
_BY_ACRONYM = {uf.acronym: uf for uf in UFS}


def by_code(code: int | str) -> UF | None:
    """Look up a state by its IBGE ``cUF`` code, or ``None`` when unknown."""
    try:
        return _BY_CODE.get(int(code))
    except (TypeError, ValueError):
        return None


def by_acronym(acronym: str) -> UF | None:
    """Look up a state by its two-letter acronym, or ``None`` when unknown."""
    if not acronym:
        return None
    return _BY_ACRONYM.get(acronym.strip().upper())


def is_valid_uf_code(code: int | str) -> bool:
    """Return ``True`` when *code* is a recognized IBGE state code."""
    return by_code(code) is not None
