"""Tests for the mechanical-fix layer.

The conservatism is the feature. Only rules whose correct edit follows from the
pattern alone carry a rewrite, and the tests below assert both halves: that the
fixable ones are fixed, and that the ones needing judgement are left untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fiscalkit.scan import RULES, scan_path
from fiscalkit.scan.fixer import apply_patches, build_patches, unified_diff

LEGACY_VALIDATORS = (
    "import re\n"
    "\n"
    'CNPJ_RE = re.compile(r"^\\d{14}$")\n'
    "\n"
    "\n"
    "def normalizar(valor):\n"
    '    return re.sub(r"\\D", "", valor)\n'
    "\n"
    "\n"
    "def validar(cnpj):\n"
    "    return int(normalizar(cnpj))\n"
)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "validators.py").write_text(LEGACY_VALIDATORS, encoding="utf-8")
    (tmp_path / "models.py").write_text(
        "cnpj = models.BigIntegerField(unique=True)\n", encoding="utf-8"
    )
    (tmp_path / "schema.sql").write_text(
        "CREATE TABLE f (cnpj BIGINT NOT NULL UNIQUE);\n", encoding="utf-8"
    )
    return tmp_path


def test_only_unambiguous_rules_declare_a_rewrite() -> None:
    """`int(cnpj)` has no mechanical fix and must not pretend to.

    Repairing it means the surrounding code stops treating a CNPJ as a number,
    which no line-level rewrite can do. A tool that guessed would emit a
    plausible diff that silently changed behaviour.
    """
    fixable = {r.id for r in RULES if r.is_fixable}
    assert fixable == {"CNPJ001", "CNPJ011", "CNPJ012", "CNPJ021"}
    for rule_id in ("CNPJ010", "CNPJ003", "CNPJ004", "CNPJ013"):
        rule = next(r for r in RULES if r.id == rule_id)
        assert not rule.is_fixable, f"{rule_id} must stay a human decision"


def test_patches_rewrite_what_they_should(project) -> None:
    patches = build_patches(scan_path(project).findings, project)
    combined = "\n".join(p.patched for p in patches)
    assert "[0-9A-Z]{12}[0-9]{2}" in combined
    assert "[^0-9A-Z]" in combined
    assert "models.CharField(max_length=14, unique=True)" in combined
    assert "CHAR(14)" in combined
    # The judgement call survives untouched.
    assert "int(normalizar(cnpj))" in combined


def test_diff_is_in_git_apply_shape(project) -> None:
    diff = unified_diff(build_patches(scan_path(project).findings, project), project)
    assert diff.startswith("--- a/")
    assert "+++ b/" in diff
    assert "@@" in diff
    # Relative, forward-slashed paths, which is what `git apply` needs.
    for line in diff.splitlines():
        if line.startswith(("--- a/", "+++ b/")):
            assert not line.split("/", 1)[1].startswith("/")


def test_applying_resolves_the_fixable_findings_only(project) -> None:
    before = scan_path(project)
    written = apply_patches(build_patches(before.findings, project))
    assert len(written) == 3

    after = scan_path(project)
    remaining = {f.rule_id for f in after.findings}
    assert remaining == {"CNPJ010"}, remaining
    assert len(after.findings) < len(before.findings)


def test_applying_twice_is_a_no_op(project) -> None:
    """The rewrite must be idempotent; a second run has nothing left to change."""
    apply_patches(build_patches(scan_path(project).findings, project))
    second = build_patches(scan_path(project).findings, project)
    assert second == []


def test_a_clean_project_produces_no_patches(tmp_path) -> None:
    (tmp_path / "ok.py").write_text(
        "from fiscalkit import is_valid_cnpj\n\n\ndef check(v):\n    return is_valid_cnpj(v)\n",
        encoding="utf-8",
    )
    assert build_patches(scan_path(tmp_path).findings, tmp_path) == []


def test_unreadable_file_is_skipped_not_fatal(project) -> None:
    findings = scan_path(project).findings
    for finding in findings:
        object.__setattr__(finding, "path", "does/not/exist.py")
    assert build_patches(findings, project) == []


def test_patch_is_built_against_the_file_as_it_is_now(project) -> None:
    """Patches read the file fresh rather than trusting the stored excerpt."""
    findings = scan_path(project).findings
    (project / "schema.sql").write_text(
        "CREATE TABLE f (cnpj CHAR(14) NOT NULL UNIQUE);\n", encoding="utf-8"
    )
    patched = {Path(p.path).name for p in build_patches(findings, project)}
    assert "schema.sql" not in patched
