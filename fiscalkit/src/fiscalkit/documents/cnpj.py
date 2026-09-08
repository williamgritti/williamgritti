"""CNPJ parsing, validation and formatting, including the alphanumeric format.

The CNPJ identifies legal entities in Brazil. Historically it was 14 numeric
digits. Instrução Normativa RFB nº 2.229/2024 introduces the *alphanumeric* CNPJ:
from July 2026 newly issued numbers may contain ``A``-``Z`` in the first twelve
positions, while the two check digits stay numeric.

Both forms are handled by a single algorithm. The check-digit computation converts
each character with ``ord(c) - 48``, which maps ``"0"``-``"9"`` onto ``0``-``9``
and therefore reproduces the legacy numeric result exactly. A purely numeric CNPJ
validates identically under either reading, so callers need no feature flag.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..exceptions import ValidationError

__all__ = [
    "CNPJ",
    "format_cnpj",
    "is_alphanumeric_cnpj",
    "is_valid_cnpj",
    "strip_cnpj",
]

# Only 0-9 and A-Z are valid CNPJ characters; everything else is punctuation.
_NON_ALNUM = re.compile(r"[^0-9A-Z]")
_CNPJ_LENGTH = 14
_BASE_LENGTH = 12  # positions before the two check digits

# Weight vectors are shared with the legacy numeric algorithm.
_DV1_WEIGHTS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_DV2_WEIGHTS = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)

_REPDIGIT = {d * _CNPJ_LENGTH for d in "0123456789"}


def strip_cnpj(value: str) -> str:
    """Uppercase *value* and drop every character that is not ``0-9`` or ``A-Z``."""
    return _NON_ALNUM.sub("", (value or "").upper())


def _char_value(char: str) -> int:
    """Map a CNPJ character to its numeric weight input.

    Per IN RFB nº 2.229/2024 the value is the ASCII code minus 48, so ``"0"`` is 0,
    ``"9"`` is 9, ``"A"`` is 17 and ``"Z"`` is 42.
    """
    return ord(char) - 48


def _check_digit(base: str, weights: tuple[int, ...]) -> int:
    """Compute one mod-11 check digit over *base* using *weights*."""
    total = sum(_char_value(c) * w for c, w in zip(base, weights, strict=True))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def is_alphanumeric_cnpj(value: str) -> bool:
    """Return ``True`` when *value* uses at least one letter in its base.

    Useful for routing: some downstream systems still reject letters, and knowing
    this up front lets a caller warn before transmitting.
    """
    base = strip_cnpj(value)[:_BASE_LENGTH]
    return any(c.isalpha() for c in base)


def is_valid_cnpj(value: str) -> bool:
    """Return ``True`` when *value* is a structurally valid CNPJ.

    Accepts both the legacy numeric form and the alphanumeric form. Punctuation is
    ignored. This validates structure and check digits only; it does not tell you
    whether the CNPJ is registered or active.
    """
    cleaned = strip_cnpj(value)
    if len(cleaned) != _CNPJ_LENGTH or cleaned in _REPDIGIT:
        return False
    # The two check digits are numeric in both the legacy and alphanumeric formats.
    if not cleaned[_BASE_LENGTH:].isdigit():
        return False
    dv1 = _check_digit(cleaned[:_BASE_LENGTH], _DV1_WEIGHTS)
    dv2 = _check_digit(cleaned[: _BASE_LENGTH + 1], _DV2_WEIGHTS)
    return cleaned[12] == str(dv1) and cleaned[13] == str(dv2)


def format_cnpj(value: str) -> str:
    """Render *value* in the canonical ``00.000.000/0000-00`` form."""
    cleaned = strip_cnpj(value)
    if len(cleaned) != _CNPJ_LENGTH:
        raise ValidationError(
            f"CNPJ must have {_CNPJ_LENGTH} characters, got {len(cleaned)}",
            value=cleaned,
            reason="length",
        )
    return f"{cleaned[:2]}.{cleaned[2:5]}.{cleaned[5:8]}/{cleaned[8:12]}-{cleaned[12:]}"


def check_digits_for(base: str) -> str:
    """Return the two check digits for a 12-character CNPJ *base*.

    Handy when generating test fixtures or completing a partially known number.

    Raises:
        ValidationError: If *base* is not exactly 12 valid characters.
    """
    cleaned = strip_cnpj(base)
    if len(cleaned) != _BASE_LENGTH:
        raise ValidationError(
            f"CNPJ base must have {_BASE_LENGTH} characters, got {len(cleaned)}",
            value=cleaned,
            reason="length",
        )
    dv1 = _check_digit(cleaned, _DV1_WEIGHTS)
    dv2 = _check_digit(cleaned + str(dv1), _DV2_WEIGHTS)
    return f"{dv1}{dv2}"


@dataclass(frozen=True, slots=True)
class CNPJ:
    """A validated CNPJ, numeric or alphanumeric."""

    value: str

    @classmethod
    def parse(cls, value: str) -> CNPJ:
        """Validate *value* and return a :class:`CNPJ`.

        Raises:
            ValidationError: If the length, character set, repeated-digit or
                check-digit rules fail.
        """
        cleaned = strip_cnpj(value)
        if len(cleaned) != _CNPJ_LENGTH:
            raise ValidationError(
                f"CNPJ must have {_CNPJ_LENGTH} characters, got {len(cleaned)}",
                value=cleaned,
                reason="length",
            )
        if cleaned in _REPDIGIT:
            raise ValidationError(
                "CNPJ with all digits repeated is never issued",
                value=cleaned,
                reason="repeated_digits",
            )
        if not cleaned[_BASE_LENGTH:].isdigit():
            raise ValidationError(
                "CNPJ check digits must be numeric even in the alphanumeric format",
                value=cleaned,
                reason="non_numeric_check_digits",
            )
        if not is_valid_cnpj(cleaned):
            raise ValidationError(
                "CNPJ check digits do not match",
                value=cleaned,
                reason="check_digit",
            )
        return cls(cleaned)

    @property
    def formatted(self) -> str:
        """The CNPJ in ``00.000.000/0000-00`` form."""
        return format_cnpj(self.value)

    @property
    def is_alphanumeric(self) -> bool:
        """Whether this CNPJ uses the post-2026 alphanumeric format."""
        return is_alphanumeric_cnpj(self.value)

    @property
    def raiz(self) -> str:
        """The 8-character root shared by every establishment of the company."""
        return self.value[:8]

    @property
    def ordem(self) -> str:
        """The 4-character branch order; ``"0001"`` is the headquarters."""
        return self.value[8:12]

    @property
    def is_matriz(self) -> bool:
        """Whether this CNPJ identifies the headquarters rather than a branch."""
        return self.ordem == "0001"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.formatted
