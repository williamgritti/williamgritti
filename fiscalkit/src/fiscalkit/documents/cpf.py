"""CPF (Cadastro de Pessoas Físicas) parsing, validation and formatting.

The CPF is an 11-digit Brazilian taxpayer identifier for natural persons. The last
two digits are mod-11 check digits computed over the preceding digits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..exceptions import ValidationError

__all__ = ["CPF", "format_cpf", "is_valid_cpf", "strip_cpf"]

_NON_DIGIT = re.compile(r"\D")
_CPF_LENGTH = 11

# A CPF made of a single repeated digit passes the mod-11 arithmetic but is never
# issued by the Receita Federal, so these are rejected explicitly.
_REPDIGIT = {d * _CPF_LENGTH for d in "0123456789"}


def strip_cpf(value: str) -> str:
    """Return *value* with every non-digit character removed."""
    return _NON_DIGIT.sub("", value or "")


def _check_digit(digits: str, start_weight: int) -> int:
    """Compute one mod-11 check digit over *digits* with descending weights.

    Weights run from *start_weight* down to 2. A remainder below 2 yields a check
    digit of 0, which is the rule the Receita Federal specifies.
    """
    total = sum(int(d) * w for d, w in zip(digits, range(start_weight, 1, -1), strict=True))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_cpf(value: str) -> bool:
    """Return ``True`` when *value* is a structurally valid CPF.

    Punctuation is ignored, so ``"111.444.777-35"`` and ``"11144477735"`` are
    treated identically. This checks the check digits only; it cannot tell you
    whether the CPF was actually issued or is currently active.
    """
    digits = strip_cpf(value)
    if len(digits) != _CPF_LENGTH or digits in _REPDIGIT:
        return False
    first = _check_digit(digits[:9], 10)
    second = _check_digit(digits[:10], 11)
    return digits[9] == str(first) and digits[10] == str(second)


def format_cpf(value: str) -> str:
    """Render *value* in the canonical ``000.000.000-00`` form."""
    digits = strip_cpf(value)
    if len(digits) != _CPF_LENGTH:
        raise ValidationError(
            f"CPF must have {_CPF_LENGTH} digits, got {len(digits)}",
            value=digits,
            reason="length",
        )
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


@dataclass(frozen=True, slots=True)
class CPF:
    """A validated CPF.

    Construct through :meth:`parse` to get validation; the constructor itself
    trusts its input so that already-validated values can be rebuilt cheaply.
    """

    digits: str

    @classmethod
    def parse(cls, value: str) -> CPF:
        """Validate *value* and return a :class:`CPF`.

        Raises:
            ValidationError: If the length, repeated-digit or check-digit rules fail.
        """
        digits = strip_cpf(value)
        if len(digits) != _CPF_LENGTH:
            raise ValidationError(
                f"CPF must have {_CPF_LENGTH} digits, got {len(digits)}",
                value=digits,
                reason="length",
            )
        if digits in _REPDIGIT:
            raise ValidationError(
                "CPF with all digits repeated is never issued",
                value=digits,
                reason="repeated_digits",
            )
        if not is_valid_cpf(digits):
            raise ValidationError(
                "CPF check digits do not match",
                value=digits,
                reason="check_digit",
            )
        return cls(digits)

    @property
    def formatted(self) -> str:
        """The CPF in ``000.000.000-00`` form."""
        return format_cpf(self.digits)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.formatted
