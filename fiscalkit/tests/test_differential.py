"""Differential tests against independent reference implementations.

Every other correctness test here was written by the same author as the code it
checks, so a misreading of the specification would be reproduced faithfully on
both sides and pass. These tests instead compare against two libraries written
by other people from the same published rules: ``brutils`` and ``validate-docbr``.

Agreement across tens of thousands of generated cases is meaningfully stronger
evidence than any number of hand-picked examples. A disagreement means one of the
three is wrong, which is worth knowing whichever one it turns out to be.

Skipped when the reference libraries are absent, so the suite still runs with no
extra dependencies. CI installs them and runs this.
"""

from __future__ import annotations

import random

import pytest

from fiscalkit import is_valid_cnpj, is_valid_cpf
from fiscalkit.documents.cnpj import check_digits_for

brutils = pytest.importorskip("brutils", reason="reference implementation not installed")
validate_docbr = pytest.importorskip(
    "validate_docbr", reason="reference implementation not installed"
)

#: Enough to exercise every remainder class of the mod-11 arithmetic many times
#: over, while keeping the suite fast enough to run on every push.
CASES = 5_000
SEED = 20260908

ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"


@pytest.fixture(scope="module")
def references():
    return {
        "brutils": (brutils.is_valid_cpf, brutils.is_valid_cnpj),
        "validate-docbr": (
            validate_docbr.CPF().validate,
            validate_docbr.CNPJ().validate,
        ),
    }


def _cpf_with_check_digits(base: str) -> str:
    digits = [int(c) for c in base]
    for length in (9, 10):
        total = sum(digits[i] * ((length + 1) - i) for i in range(length))
        digits.append((total * 10) % 11 % 10)
    return "".join(str(d) for d in digits)


def _corrupt(value: str, rng: random.Random, alphabet: str, positions: int) -> str:
    index = rng.randrange(positions)
    return value[:index] + rng.choice(alphabet) + value[index + 1 :]


@pytest.mark.parametrize("reference", ["brutils", "validate-docbr"])
def test_numeric_cnpj_matches_reference(reference: str, references) -> None:
    """Half valid, half corrupted in one position, so both verdicts are exercised."""
    _, ref = references[reference]
    rng = random.Random(SEED)
    disagreements = []
    for _ in range(CASES):
        base = "".join(rng.choice(DIGITS) for _ in range(12))
        candidate = base + check_digits_for(base)
        if rng.random() < 0.5:
            candidate = _corrupt(candidate, rng, DIGITS, 14)
        if is_valid_cnpj(candidate) != ref(candidate):
            disagreements.append(candidate)
    assert not disagreements, f"{len(disagreements)} disagreements, e.g. {disagreements[:5]}"


@pytest.mark.parametrize("reference", ["brutils", "validate-docbr"])
def test_alphanumeric_cnpj_matches_reference(reference: str, references) -> None:
    """The 2026 format, which is where an ASCII-mapping error would surface."""
    _, ref = references[reference]
    rng = random.Random(SEED + 1)
    disagreements = []
    for _ in range(CASES):
        base = "".join(rng.choice(ALNUM) for _ in range(12))
        candidate = base + check_digits_for(base)
        if rng.random() < 0.5:
            candidate = _corrupt(candidate, rng, ALNUM, 12)
        if is_valid_cnpj(candidate) != ref(candidate):
            disagreements.append(candidate)
    assert not disagreements, f"{len(disagreements)} disagreements, e.g. {disagreements[:5]}"


@pytest.mark.parametrize("reference", ["brutils", "validate-docbr"])
def test_cpf_matches_reference(reference: str, references) -> None:
    ref, _ = references[reference]
    rng = random.Random(SEED + 2)
    disagreements = []
    for _ in range(CASES):
        base = "".join(rng.choice(DIGITS) for _ in range(9))
        candidate = _cpf_with_check_digits(base)
        if rng.random() < 0.5:
            candidate = _corrupt(candidate, rng, DIGITS, 11)
        if is_valid_cpf(candidate) != ref(candidate):
            disagreements.append(candidate)
    assert not disagreements, f"{len(disagreements)} disagreements, e.g. {disagreements[:5]}"


def test_generated_check_digits_are_accepted_by_references(references) -> None:
    """`check_digits_for` is fiscalkit's own; the references must accept its output.

    This is the direction that would catch a generator that agrees with our own
    validator because both share the same mistake.
    """
    rng = random.Random(SEED + 3)
    for _ in range(1_000):
        base = "".join(rng.choice(ALNUM) for _ in range(12))
        full = base + check_digits_for(base)
        for name, (_, ref) in references.items():
            assert ref(full), f"{name} rejected our generated CNPJ {full}"


def test_reference_libraries_are_actually_being_exercised(references) -> None:
    """Guard against a reference that silently accepts or rejects everything.

    A stubbed or broken reference would make every test above pass vacuously.
    """
    for name, (cpf_ref, cnpj_ref) in references.items():
        assert cnpj_ref("11222333000181") is True, f"{name} rejects a known-valid CNPJ"
        assert cnpj_ref("11222333000182") is False, f"{name} accepts a bad check digit"
        assert cpf_ref("11144477735") is True, f"{name} rejects a known-valid CPF"
        assert cpf_ref("11144477736") is False, f"{name} accepts a bad CPF"


@pytest.mark.parametrize("reference", ["brutils", "validate-docbr"])
def test_letters_in_check_digit_positions_match_reference(reference: str, references) -> None:
    """The two check digits stay numeric; the references must agree that they do.

    Every other case here corrupts only the first twelve positions, so this
    asymmetry -- the defining detail of IN RFB 2.229/2024 -- was never compared
    against an implementation written by someone else. A letter in position 13 or
    14 must be rejected by all three.
    """
    _, ref = references[reference]
    rng = random.Random(SEED + 4)
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    disagreements = []
    for _ in range(1_000):
        base = "".join(rng.choice(ALNUM) for _ in range(12))
        digits = check_digits_for(base)
        for candidate in (
            base + rng.choice(letters) + digits[1],
            base + digits[0] + rng.choice(letters),
            base + rng.choice(letters) + rng.choice(letters),
        ):
            ours, theirs = is_valid_cnpj(candidate), ref(candidate)
            if ours != theirs:
                disagreements.append((candidate, ours, theirs))
            if ours is not False:
                disagreements.append((candidate, "we accepted a letter as a check digit", ours))
    assert not disagreements, f"{len(disagreements)} disagreements, e.g. {disagreements[:5]}"
