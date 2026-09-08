"""CFOP (Código Fiscal de Operações e Prestações) classification.

A CFOP is four digits. The first digit alone determines the direction of the
operation and the counterpart's location, which is the fact most callers actually
need. The remaining three digits identify the specific nature of the operation;
the full table is long, versioned by CONFAZ, and deliberately not embedded here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["CFOPInfo", "classify_cfop", "is_valid_cfop", "strip_cfop"]

_NON_DIGIT = re.compile(r"\D")

# First digit -> (direction, scope). Direction is from the issuer's point of view.
_FIRST_DIGIT = {
    "1": ("entrada", "interna", "Entrada dentro do próprio estado"),
    "2": ("entrada", "interestadual", "Entrada de outro estado"),
    "3": ("entrada", "exterior", "Entrada do exterior (importação)"),
    "5": ("saida", "interna", "Saída dentro do próprio estado"),
    "6": ("saida", "interestadual", "Saída para outro estado"),
    "7": ("saida", "exterior", "Saída para o exterior (exportação)"),
}


def strip_cfop(value: str | int) -> str:
    """Return *value* as a bare digit string."""
    return _NON_DIGIT.sub("", str(value or ""))


@dataclass(frozen=True, slots=True)
class CFOPInfo:
    """What the first digit of a CFOP tells you about the operation."""

    code: str
    direction: str
    """``"entrada"`` or ``"saida"``."""
    scope: str
    """``"interna"``, ``"interestadual"`` or ``"exterior"``."""
    description: str

    @property
    def is_entrada(self) -> bool:
        """Whether the operation is inbound for the document's issuer."""
        return self.direction == "entrada"

    @property
    def is_saida(self) -> bool:
        """Whether the operation is outbound for the document's issuer."""
        return self.direction == "saida"

    @property
    def crosses_border(self) -> bool:
        """Whether the operation involves import or export."""
        return self.scope == "exterior"


def is_valid_cfop(value: str | int) -> bool:
    """Return ``True`` when *value* is four digits starting with a known prefix."""
    digits = strip_cfop(value)
    return len(digits) == 4 and digits[0] in _FIRST_DIGIT


def classify_cfop(value: str | int) -> CFOPInfo | None:
    """Classify a CFOP, or return ``None`` when it is malformed.

    Only the first digit is interpreted, which is what determines direction and
    scope. The specific operation nature encoded in the last three digits is left
    to the caller, since that table changes with CONFAZ rulings.
    """
    digits = strip_cfop(value)
    if not is_valid_cfop(digits):
        return None
    direction, scope, description = _FIRST_DIGIT[digits[0]]
    return CFOPInfo(code=digits, direction=direction, scope=scope, description=description)
