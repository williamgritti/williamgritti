"""Tests for the 44-digit access key decoder."""

from __future__ import annotations

import random
from datetime import date

import pytest

from fiscalkit import AccessKey, ValidationError, is_valid_access_key
from fiscalkit.nfe.chave import access_key_check_digit, format_access_key


def build_key(
    *,
    uf: str = "43",
    year_month: str = "2403",
    cnpj: str = "11222333000181",
    model: str = "55",
    series: str = "001",
    number: str = "000000123",
    emission: str = "1",
    code: str = "00000001",
) -> str:
    """Assemble a valid key from its parts, appending the computed check digit."""
    body = f"{uf}{year_month}{cnpj}{model}{series}{number}{emission}{code}"
    assert len(body) == 43, f"body is {len(body)} digits, expected 43"
    return body + str(access_key_check_digit(body))


def random_body(rng: random.Random) -> str:
    """A random 43-digit body whose AAMM month is in range.

    Fully random digits give a valid month only ~12% of the time, and an
    out-of-range month is rejected before the check digit is ever consulted, so
    tests about check-digit behaviour must pin the month first.
    """
    digits = [rng.choice("0123456789") for _ in range(43)]
    digits[2] = rng.choice("0123456789")
    digits[3] = rng.choice("0123456789")
    month = rng.randint(1, 12)
    digits[4], digits[5] = f"{month:02d}"
    return "".join(digits)


def reference_check_digit(body: str) -> int:
    """A second, deliberately different implementation of the mod-11 rule.

    The library walks the string right-to-left advancing the weight; this builds
    the weight vector up front and zips it. Agreement between two independently
    written formulations is what makes the check meaningful.
    """
    weights = [2 + (i % 8) for i in range(len(body))]
    total = sum(int(d) * w for d, w in zip(reversed(body), weights, strict=True))
    remainder = total % 11
    return 0 if remainder in (0, 1) else 11 - remainder


def test_check_digit_matches_independent_implementation() -> None:
    """Both formulations must agree across a wide spread of random bodies."""
    rng = random.Random(20260908)
    for _ in range(2000):
        body = "".join(rng.choice("0123456789") for _ in range(43))
        assert access_key_check_digit(body) == reference_check_digit(body)


def test_round_trip_build_and_parse() -> None:
    key = build_key()
    assert is_valid_access_key(key)
    assert AccessKey.parse(key).digits == key


def test_fields_decode_to_their_inputs() -> None:
    key = build_key(
        uf="35",
        year_month="2601",
        cnpj="11222333000181",
        model="65",
        series="004",
        number="000009999",
        emission="9",
        code="12345678",
    )
    parsed = AccessKey.parse(key)
    assert parsed.uf_code == "35"
    assert parsed.uf is not None and parsed.uf.acronym == "SP"
    assert parsed.uf.name == "São Paulo"
    assert parsed.year_month == "2601"
    assert parsed.emitted_on == date(2026, 1, 1)
    assert parsed.cnpj == "11222333000181"
    assert parsed.model == "65"
    assert parsed.model_name.startswith("NFC-e")
    assert parsed.series == "004"
    assert parsed.number == "000009999"
    assert parsed.emission_type == "9"
    assert parsed.is_contingency
    assert parsed.numeric_code == "12345678"


def test_normal_emission_is_not_contingency() -> None:
    parsed = AccessKey.parse(build_key(emission="1"))
    assert not parsed.is_contingency
    assert parsed.emission_type_name == "Normal"


def test_rio_grande_do_sul_key_resolves_state() -> None:
    parsed = AccessKey.parse(build_key(uf="43"))
    assert parsed.uf is not None
    assert parsed.uf.acronym == "RS"
    assert parsed.uf.region == "Sul"


def test_punctuation_and_whitespace_are_ignored() -> None:
    key = build_key()
    spaced = format_access_key(key)
    assert " " in spaced
    assert AccessKey.parse(spaced).digits == key


def test_wrong_check_digit_rejected() -> None:
    key = build_key()
    wrong = key[:43] + str((int(key[43]) + 1) % 10)
    assert not is_valid_access_key(wrong)
    with pytest.raises(ValidationError) as exc:
        AccessKey.parse(wrong)
    assert exc.value.reason == "check_digit"


def _undetected_substitutions(key: str) -> list[tuple[int, str, str]]:
    """Every single-digit substitution in *key* that still validates."""
    misses = []
    for position in range(43):
        if position in (4, 5):
            continue  # month positions are rejected by the month rule, not the DV
        original = key[position]
        for replacement in "0123456789":
            if replacement == original:
                continue
            mutated = key[:position] + replacement + key[position + 1 :]
            if is_valid_access_key(mutated):
                misses.append((position, original, replacement))
    return misses


def test_single_digit_changes_detected_when_check_digit_is_nonzero() -> None:
    """With a non-zero check digit, mod-11 catches every single-digit typo."""
    rng = random.Random(11)
    checked = 0
    while checked < 25:
        body = random_body(rng)
        key = body + str(access_key_check_digit(body))
        if key[43] == "0":
            continue
        assert _undetected_substitutions(key) == []
        checked += 1


def test_zero_check_digit_is_a_weaker_guard() -> None:
    """Remainders 0 and 1 both collapse to check digit 0, so some typos survive.

    This is a property of the scheme the NF-e manual specifies, not a defect here,
    and it is why the check digit is a transcription guard rather than a tamper
    seal. Roughly two keys in eleven land on check digit 0.
    """
    rng = random.Random(13)
    while True:
        body = random_body(rng)
        key = body + str(access_key_check_digit(body))
        if key[43] == "0":
            break
    misses = _undetected_substitutions(key)
    assert misses, "expected the zero-check-digit collapse to admit some substitutions"
    # Every surviving mutation must itself still carry check digit 0.
    for position, _, replacement in misses:
        mutated = key[:position] + replacement + key[position + 1 :]
        assert mutated[43] == "0"


def test_wrong_length_rejected() -> None:
    for bad in ("", "123", "1" * 43, "1" * 45):
        assert not is_valid_access_key(bad)
        with pytest.raises(ValidationError):
            AccessKey.parse(bad)


def test_check_digit_requires_43_digits() -> None:
    with pytest.raises(ValidationError) as exc:
        access_key_check_digit("123")
    assert exc.value.reason == "length"


def test_unknown_uf_code_degrades_gracefully() -> None:
    """Code 99 is not an IBGE state; the key still parses, uf is just None."""
    parsed = AccessKey.parse(build_key(uf="99"))
    assert parsed.uf is None
    assert parsed.to_dict()["uf_sigla"] is None


def test_unknown_model_gets_fallback_name() -> None:
    parsed = AccessKey.parse(build_key(model="99"))
    assert "desconhecido" in parsed.model_name


def test_to_dict_is_json_serializable() -> None:
    import json

    payload = AccessKey.parse(build_key()).to_dict()
    assert json.loads(json.dumps(payload))["uf_sigla"] == "RS"
