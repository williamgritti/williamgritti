"""Tests for the mechanical-fix layer.

The conservatism is the feature. Only rules whose correct edit follows from the
pattern alone carry a rewrite, and the tests below assert both halves: that the
fixable ones are fixed, and that the ones needing judgement are left untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fiscalkit.scan import RULES, scan_path
from fiscalkit.scan.fixer import FilePatch, apply_patches, build_patches, unified_diff

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
    applied = apply_patches(build_patches(before.findings, project))
    assert len(applied.written) == 3
    assert applied.ok, applied.failed

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


def test_a_failed_write_is_reported_and_does_not_abort_the_rest(tmp_path) -> None:
    """One unwritable file must not cost the caller the record of the others.

    Patches are written one at a time, so raising on the second of several left
    the tree half-modified and the caller holding a traceback instead of the list
    of what had already changed -- from a tool whose entire job is editing source
    files. The scanner already treats an unreadable file as something to report
    and carry on from; this asserts the write path matches it.
    """
    ok = tmp_path / "ok.py"
    ok.write_text("x = 1\n", encoding="utf-8")

    patches = [
        FilePatch(path=ok, original="x = 1\n", patched="x = 2\n", rule_ids=("CNPJ001",)),
        FilePatch(
            path=tmp_path / "sem-tal-pasta" / "f.py",
            original="a\n",
            patched="b\n",
            rule_ids=("CNPJ001",),
        ),
        # Ordered last on purpose: a failure in the middle must not skip it.
        FilePatch(
            path=tmp_path / "depois.py",
            original="y = 1\n",
            patched="y = 2\n",
            rule_ids=("CNPJ001",),
        ),
    ]
    (tmp_path / "depois.py").write_text("y = 1\n", encoding="utf-8")

    applied = apply_patches(patches)

    assert applied.ok is False
    assert [p.name for p in applied.written] == ["ok.py", "depois.py"]
    assert len(applied.failed) == 1
    failed_path, reason = applied.failed[0]
    assert failed_path.name == "f.py"
    assert reason, "the failure must carry a reason the caller can print"

    assert ok.read_text(encoding="utf-8") == "x = 2\n"
    assert (tmp_path / "depois.py").read_text(encoding="utf-8") == "y = 2\n"


def test_cli_fix_exits_non_zero_when_a_write_fails(tmp_path, capsys, monkeypatch) -> None:
    """A partly rewritten tree must not report success to a build gate.

    Isolating this needs care. A refused write leaves the finding in the tree, so
    the re-scan still reports breakage and the CLI would exit 1 for that reason
    alone -- a test that only asserts "exit 1" therefore passes with the guard
    deleted, which is how the first version of this test was worthless. The
    re-scan is stubbed clean so the ONLY thing that can produce a non-zero exit
    is the failed write.
    """
    from fiscalkit import cli
    from fiscalkit.scan.scanner import ScanResult

    (tmp_path / "f.py").write_text(
        'import re\nCNPJ_RE = re.compile(r"^\\d{14}$")\n', encoding="utf-8"
    )

    real_scan = cli.scan_path
    calls = {"n": 0}

    def scan_then_pretend_clean(target, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            return real_scan(target, **kwargs)
        return ScanResult()  # the post-fix re-scan: nothing left to report

    real_open = Path.open

    def refuse_writes(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if args and args[0] == "w":
            raise PermissionError(13, "Permission denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(cli, "scan_path", scan_then_pretend_clean)
    monkeypatch.setattr(Path, "open", refuse_writes)
    exit_code = cli.main(["scan", str(tmp_path), "--fix"])
    monkeypatch.undo()

    captured = capsys.readouterr()
    assert calls["n"] == 2, "the re-scan must have happened for this to be isolated"
    assert "0 arquivo(s) alterado(s)" in captured.out
    assert "não foi possível gravar" in captured.err
    assert exit_code == 1, "a failed write must not exit 0 even when nothing remains"


def test_build_patches_ignores_a_finding_whose_rule_is_unknown(tmp_path) -> None:
    """A finding naming a rule that no longer exists must be skipped, not crash.

    `build_patches` guards with `rule is not None and rule.is_fixable`. Nothing
    exercised the None half, so mutating the `and` to `or` -- which makes an
    unknown rule id raise AttributeError on None -- left the suite green. That is
    the shape of a defensive check nobody has ever defended against: it survives
    review because it looks careful, and it is unverified.
    """
    from fiscalkit.scan.scanner import Finding

    target = tmp_path / "f.py"
    target.write_text('CNPJ_RE = r"^\\d{14}$"\n', encoding="utf-8")

    stale = Finding(
        rule_id="CNPJ999",
        title="uma regra que não existe mais",
        severity="breaks",
        path="f.py",
        line=1,
        excerpt='CNPJ_RE = r"^\\d{14}$"',
        explanation="",
        fix="",
    )
    assert build_patches([stale], tmp_path) == []
    assert target.read_text(encoding="utf-8") == 'CNPJ_RE = r"^\\d{14}$"\n'
