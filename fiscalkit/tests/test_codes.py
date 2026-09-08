"""Tests for the UF and CFOP lookup tables."""

from __future__ import annotations

import pytest

from fiscalkit import UFS, by_acronym, by_code, classify_cfop, is_valid_cfop, is_valid_uf_code


def test_all_27_federative_units_present() -> None:
    """26 states plus the Federal District."""
    assert len(UFS) == 27
    assert len({uf.code for uf in UFS}) == 27
    assert len({uf.acronym for uf in UFS}) == 27


@pytest.mark.parametrize(
    ("code", "acronym", "region"),
    [(43, "RS", "Sul"), (35, "SP", "Sudeste"), (53, "DF", "Centro-Oeste"), (13, "AM", "Norte")],
)
def test_lookup_by_code(code: int, acronym: str, region: str) -> None:
    uf = by_code(code)
    assert uf is not None
    assert uf.acronym == acronym
    assert uf.region == region


def test_lookup_accepts_zero_padded_string() -> None:
    """Access keys carry cUF as a two-character string, sometimes zero-padded."""
    assert by_code("43") == by_code(43)


def test_lookup_by_acronym_is_case_and_space_insensitive() -> None:
    assert by_acronym(" rs ") == by_code(43)


def test_unknown_lookups_return_none() -> None:
    assert by_code(99) is None
    assert by_code("nonsense") is None
    assert by_code(None) is None
    assert by_acronym("XX") is None
    assert by_acronym("") is None
    assert not is_valid_uf_code(99)


def test_code_34_is_not_a_state() -> None:
    """The IBGE codes are non-contiguous; 34 and 36 through 40 are unassigned."""
    for gap in (30, 34, 36, 40, 44):
        assert by_code(gap) is None


@pytest.mark.parametrize(
    ("cfop", "direction", "scope"),
    [
        ("1102", "entrada", "interna"),
        ("2102", "entrada", "interestadual"),
        ("3102", "entrada", "exterior"),
        ("5102", "saida", "interna"),
        ("6102", "saida", "interestadual"),
        ("7102", "saida", "exterior"),
    ],
)
def test_cfop_classification(cfop: str, direction: str, scope: str) -> None:
    info = classify_cfop(cfop)
    assert info is not None
    assert info.direction == direction
    assert info.scope == scope
    assert info.is_entrada == (direction == "entrada")
    assert info.is_saida == (direction == "saida")
    assert info.crosses_border == (scope == "exterior")


def test_cfop_accepts_punctuation_and_integers() -> None:
    assert classify_cfop("5.102") == classify_cfop(5102)


def test_invalid_cfop_returns_none() -> None:
    for bad in ("4102", "8102", "9102", "0102", "510", "51022", "", "abcd"):
        assert not is_valid_cfop(bad)
        assert classify_cfop(bad) is None
