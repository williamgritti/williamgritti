"""Tests for CPF and CNPJ validation, including the alphanumeric CNPJ."""

from __future__ import annotations

import pytest

from fiscalkit import CNPJ, CPF, ValidationError, is_valid_cnpj, is_valid_cpf
from fiscalkit.documents.cnpj import check_digits_for, is_alphanumeric_cnpj

# ---------------------------------------------------------------------------
# CPF
# ---------------------------------------------------------------------------

# Hand-verified against the mod-11 rule in the Receita Federal specification.
VALID_CPFS = [
    "111.444.777-35",
    "11144477735",
    "529.982.247-25",
    "398.334.501-80",
    "123.456.789-09",
]

INVALID_CPFS = [
    "111.444.777-36",  # second check digit off by one
    "111.444.777-45",  # first check digit off by one
    "1114447773",  # 10 digits
    "111444777355",  # 12 digits
    "",
    "abc",
]


@pytest.mark.parametrize("value", VALID_CPFS)
def test_valid_cpf_accepted(value: str) -> None:
    assert is_valid_cpf(value)
    assert CPF.parse(value).digits == "".join(c for c in value if c.isdigit())


@pytest.mark.parametrize("value", INVALID_CPFS)
def test_invalid_cpf_rejected(value: str) -> None:
    assert not is_valid_cpf(value)
    with pytest.raises(ValidationError):
        CPF.parse(value)


@pytest.mark.parametrize("digit", list("0123456789"))
def test_repeated_digit_cpf_rejected(digit: str) -> None:
    """A CPF of one repeated digit satisfies the arithmetic but is never issued."""
    value = digit * 11
    assert not is_valid_cpf(value)
    with pytest.raises(ValidationError) as exc:
        CPF.parse(value)
    assert exc.value.reason == "repeated_digits"


def test_cpf_formatting_round_trip() -> None:
    cpf = CPF.parse("11144477735")
    assert cpf.formatted == "111.444.777-35"
    assert CPF.parse(cpf.formatted) == cpf


def test_cpf_error_carries_reason() -> None:
    with pytest.raises(ValidationError) as exc:
        CPF.parse("111.444.777-36")
    assert exc.value.reason == "check_digit"
    assert exc.value.value == "11144477736"


# ---------------------------------------------------------------------------
# CNPJ -- legacy numeric
# ---------------------------------------------------------------------------

# 11.222.333/0001-81 is verified by hand in the module docstring of cnpj.py.
VALID_CNPJS = [
    "11.222.333/0001-81",
    "11222333000181",
    "34.028.316/0001-03",
]

INVALID_CNPJS = [
    "11.222.333/0001-82",
    "11.222.333/0001-91",
    "1122233300018",
    "112223330001811",
    "",
]


@pytest.mark.parametrize("value", VALID_CNPJS)
def test_valid_cnpj_accepted(value: str) -> None:
    assert is_valid_cnpj(value)


@pytest.mark.parametrize("value", INVALID_CNPJS)
def test_invalid_cnpj_rejected(value: str) -> None:
    assert not is_valid_cnpj(value)
    with pytest.raises(ValidationError):
        CNPJ.parse(value)


def test_cnpj_structure_accessors() -> None:
    cnpj = CNPJ.parse("11.222.333/0001-81")
    assert cnpj.raiz == "11222333"
    assert cnpj.ordem == "0001"
    assert cnpj.is_matriz
    assert not cnpj.is_alphanumeric
    assert cnpj.formatted == "11.222.333/0001-81"


def test_cnpj_branch_is_not_matriz() -> None:
    base = "11222333" + "0002"
    cnpj = CNPJ.parse(base + check_digits_for(base))
    assert cnpj.ordem == "0002"
    assert not cnpj.is_matriz


# ---------------------------------------------------------------------------
# CNPJ -- alphanumeric (IN RFB 2.229/2024, mandatory from July 2026)
# ---------------------------------------------------------------------------


def test_alphanumeric_cnpj_round_trip() -> None:
    """A base containing letters produces check digits that validate."""
    base = "12ABC34501DE"
    full = base + check_digits_for(base)
    assert len(full) == 14
    assert is_valid_cnpj(full)
    assert is_alphanumeric_cnpj(full)
    assert CNPJ.parse(full).is_alphanumeric


def test_alphanumeric_cnpj_is_case_insensitive() -> None:
    base = "12ABC34501DE"
    full = base + check_digits_for(base)
    assert CNPJ.parse(full.lower()) == CNPJ.parse(full)


def test_alphanumeric_algorithm_matches_numeric_for_digit_only_input() -> None:
    """The ASCII-48 mapping must reproduce the legacy result exactly.

    This is the backward-compatibility guarantee that lets one code path serve
    both formats.
    """
    assert check_digits_for("112223330001") == "81"


def test_alphanumeric_cnpj_rejects_letter_in_check_digits() -> None:
    with pytest.raises(ValidationError) as exc:
        CNPJ.parse("12ABC34501DEA1")
    assert exc.value.reason == "non_numeric_check_digits"


def test_alphanumeric_cnpj_detects_tampering() -> None:
    """Changing one base character must invalidate the check digits."""
    base = "12ABC34501DE"
    full = base + check_digits_for(base)
    tampered = "12ABD34501DE" + full[12:]
    assert is_valid_cnpj(full)
    assert not is_valid_cnpj(tampered)


def test_check_digits_for_rejects_wrong_length() -> None:
    with pytest.raises(ValidationError) as exc:
        check_digits_for("123")
    assert exc.value.reason == "length"


def test_numeric_cnpj_not_flagged_alphanumeric() -> None:
    assert not is_alphanumeric_cnpj("11222333000181")


@pytest.mark.parametrize(
    ("value", "why"),
    [
        ("12ABC34501DEAB", "both check digits are letters"),
        ("12ABC34501DE3A", "the second check digit is a letter"),
        ("12ABC34501DEA5", "the first check digit is a letter"),
        ("12ABC34501DE-5", "punctuation cannot stand in for a check digit"),
    ],
)
def test_check_digits_must_be_numeric_even_in_the_alphanumeric_format(value: str, why: str) -> None:
    """IN RFB 2.229/2024 widens the first twelve positions only.

    The last two stay numeric, and that asymmetry is the single most distinctive
    detail of the new format -- it is why one ASCII-mapping code path can serve
    both formats at all. The guard enforcing it was covered by no test: mutating
    its `return False` to `return True` left the entire suite green, so a
    refactor could have deleted it silently. The differential suite did not cover
    it either, because it only ever corrupts the first twelve positions.
    """
    assert is_valid_cnpj(value) is False, why


def test_a_valid_alphanumeric_cnpj_still_passes() -> None:
    """Guards the test above from passing because everything is rejected."""
    assert is_valid_cnpj("12ABC34501DE35") is True
