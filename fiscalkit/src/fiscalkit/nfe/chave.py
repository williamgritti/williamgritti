"""The 44-digit access key (*chave de acesso*) that identifies a fiscal document.

Every NF-e, NFC-e, CT-e and MDF-e carries an access key that is not an opaque
identifier: it is a packed record. Decoding it locally answers questions that
would otherwise require a SEFAZ round trip -- who issued the document, when, in
which state, under which model and series.

Layout, in order::

    cUF     2   IBGE state code of the issuer
    AAMM    4   two-digit year and month of emission
    CNPJ   14   issuer's CNPJ
    mod     2   document model (55 NF-e, 65 NFC-e, 57 CT-e, 58 MDF-e)
    serie   3   series
    nNF     9   document number
    tpEmis  1   emission type (1 normal, 9 contingency, ...)
    cNF     8   numeric code chosen by the issuer
    cDV     1   mod-11 check digit over the preceding 43 digits

.. note::
   The check digit is a transcription guard, not a tamper seal. The NF-e rule
   maps remainders 0 and 1 onto the same check digit of 0, so for the roughly two
   keys in eleven whose check digit is 0, some single-digit substitutions still
   validate. Keys with a non-zero check digit do catch every single-digit change.
   Authenticity is established by the issuer's digital signature and by querying
   SEFAZ, never by the check digit alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from ..codes.uf import UF, by_code
from ..exceptions import ValidationError

__all__ = ["AccessKey", "access_key_check_digit", "format_access_key", "is_valid_access_key"]

_NON_DIGIT = re.compile(r"\D")
_KEY_LENGTH = 44

# Document models that carry a 44-digit access key.
_MODELS = {
    "55": "NF-e (Nota Fiscal Eletrônica)",
    "65": "NFC-e (Nota Fiscal de Consumidor Eletrônica)",
    "57": "CT-e (Conhecimento de Transporte Eletrônico)",
    "58": "MDF-e (Manifesto de Documentos Fiscais Eletrônicos)",
    "59": "CF-e (Cupom Fiscal Eletrônico)",
    "67": "CT-e OS (Outros Serviços)",
}

_EMISSION_TYPES = {
    "1": "Normal",
    "2": "Contingência FS-IA",
    "3": "Contingência SCAN",
    "4": "Contingência DPEC",
    "5": "Contingência FS-DA",
    "6": "Contingência SVC-AN",
    "7": "Contingência SVC-RS",
    "9": "Contingência off-line (NFC-e)",
}


def _strip(value: str) -> str:
    return _NON_DIGIT.sub("", value or "")


def _month_is_valid(year_month: str) -> bool:
    """Whether the ``AAMM`` slice carries a month in 1..12."""
    return len(year_month) == 4 and year_month[2:].isdigit() and 1 <= int(year_month[2:]) <= 12


def access_key_check_digit(first_43: str) -> int:
    """Compute the mod-11 check digit (``cDV``) for the first 43 digits of a key.

    Weights cycle 2..9 from right to left. A remainder of 0 or 1 yields 0, per the
    NF-e technical manual.

    Raises:
        ValidationError: If *first_43* is not exactly 43 digits.
    """
    digits = _strip(first_43)
    if len(digits) != _KEY_LENGTH - 1:
        raise ValidationError(
            f"Expected {_KEY_LENGTH - 1} digits to compute the check digit, got {len(digits)}",
            value=digits,
            reason="length",
        )
    total = 0
    weight = 2
    for char in reversed(digits):
        total += int(char) * weight
        weight = 2 if weight == 9 else weight + 1
    remainder = total % 11
    return 0 if remainder in (0, 1) else 11 - remainder


def is_valid_access_key(value: str) -> bool:
    """Return ``True`` when *value* is 44 digits with a matching check digit."""
    digits = _strip(value)
    if len(digits) != _KEY_LENGTH:
        return False
    if not _month_is_valid(digits[2:6]):
        return False
    try:
        return int(digits[43]) == access_key_check_digit(digits[:43])
    except ValidationError:  # pragma: no cover - guarded by the length check above
        return False


def format_access_key(value: str, *, group: int = 4) -> str:
    """Group the key into blocks of *group* digits for human reading."""
    digits = _strip(value)
    if len(digits) != _KEY_LENGTH:
        raise ValidationError(
            f"Access key must have {_KEY_LENGTH} digits, got {len(digits)}",
            value=digits,
            reason="length",
        )
    return " ".join(digits[i : i + group] for i in range(0, _KEY_LENGTH, group))


@dataclass(frozen=True, slots=True)
class AccessKey:
    """A decoded, validated 44-digit access key."""

    digits: str

    @classmethod
    def parse(cls, value: str) -> AccessKey:
        """Decode *value* into an :class:`AccessKey`.

        Punctuation and whitespace are ignored, so a key copied out of a DANFE with
        its usual four-digit grouping parses directly.

        Raises:
            ValidationError: If the length or check digit is wrong.
        """
        digits = _strip(value)
        if len(digits) != _KEY_LENGTH:
            raise ValidationError(
                f"Access key must have {_KEY_LENGTH} digits, got {len(digits)}",
                value=digits,
                reason="length",
            )
        if not _month_is_valid(digits[2:6]):
            raise ValidationError(
                f"Access key emission month must be 01-12, got {digits[4:6]}",
                value=digits,
                reason="year_month",
            )
        expected = access_key_check_digit(digits[:43])
        if int(digits[43]) != expected:
            raise ValidationError(
                f"Access key check digit is {digits[43]}, expected {expected}",
                value=digits,
                reason="check_digit",
            )
        return cls(digits)

    # -- Raw slices ---------------------------------------------------------

    @property
    def uf_code(self) -> str:
        """The two-digit IBGE state code of the issuer."""
        return self.digits[0:2]

    @property
    def year_month(self) -> str:
        """Emission period as ``AAMM``."""
        return self.digits[2:6]

    @property
    def cnpj(self) -> str:
        """The issuer's CNPJ, unformatted."""
        return self.digits[6:20]

    @property
    def model(self) -> str:
        """The two-digit document model."""
        return self.digits[20:22]

    @property
    def series(self) -> str:
        """The three-digit series."""
        return self.digits[22:25]

    @property
    def number(self) -> str:
        """The nine-digit document number."""
        return self.digits[25:34]

    @property
    def emission_type(self) -> str:
        """The single-digit emission type."""
        return self.digits[34:35]

    @property
    def numeric_code(self) -> str:
        """The eight-digit code chosen by the issuer."""
        return self.digits[35:43]

    @property
    def check_digit(self) -> str:
        """The trailing mod-11 check digit."""
        return self.digits[43:44]

    # -- Interpreted views --------------------------------------------------

    @property
    def uf(self) -> UF | None:
        """The issuing state, or ``None`` when the code is unrecognized."""
        return by_code(self.uf_code)

    @property
    def emitted_on(self) -> date:
        """First day of the emission month.

        The key stores only year and month, so the day is normalized to 1. Keys use
        a two-digit year; it is resolved into the 2000s, which covers the entire
        lifetime of the NF-e programme.

        Raises:
            ValidationError: If the key was built bypassing :meth:`parse` and its
                month is out of range. Raising inside the library's own hierarchy
                keeps a caller's ``except ValidationError`` sufficient, rather
                than leaking a ``ValueError`` from :mod:`datetime`.
        """
        if not _month_is_valid(self.year_month):
            raise ValidationError(
                f"Access key emission month must be 01-12, got {self.year_month[2:]}",
                value=self.digits,
                reason="year_month",
            )
        return date(2000 + int(self.year_month[:2]), int(self.year_month[2:]), 1)

    @property
    def model_name(self) -> str:
        """Human-readable document model, or a fallback for unknown models."""
        return _MODELS.get(self.model, f"Modelo desconhecido ({self.model})")

    @property
    def emission_type_name(self) -> str:
        """Human-readable emission type, or a fallback for unknown types."""
        return _EMISSION_TYPES.get(self.emission_type, f"Tipo desconhecido ({self.emission_type})")

    @property
    def is_contingency(self) -> bool:
        """Whether the document was issued under any contingency mode."""
        return self.emission_type not in ("1", "")

    @property
    def formatted(self) -> str:
        """The key grouped in fours, as printed on a DANFE."""
        return format_access_key(self.digits)

    def to_dict(self) -> dict[str, object]:
        """Render every decoded field as a JSON-friendly mapping."""
        uf = self.uf
        return {
            "chave": self.digits,
            "chave_formatada": self.formatted,
            "uf_codigo": self.uf_code,
            "uf_sigla": uf.acronym if uf else None,
            "uf_nome": uf.name if uf else None,
            "emissao_ano_mes": self.year_month,
            "emissao_data": self.emitted_on.isoformat(),
            "cnpj_emitente": self.cnpj,
            "modelo": self.model,
            "modelo_nome": self.model_name,
            "serie": self.series,
            "numero": self.number,
            "tipo_emissao": self.emission_type,
            "tipo_emissao_nome": self.emission_type_name,
            "contingencia": self.is_contingency,
            "codigo_numerico": self.numeric_code,
            "digito_verificador": self.check_digit,
        }

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.formatted
