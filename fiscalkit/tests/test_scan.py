"""Tests for the 2026 alphanumeric-CNPJ readiness scanner."""

from __future__ import annotations

import re

import pytest

from fiscalkit.scan import RULES, scan_path, scan_text
from fiscalkit.scan.rules import BREAKS, SEVERITY_ORDER, language_of

LEGACY = "11222333000181"  # valid numeric CNPJ
ALPHA = "12ABC34501DE35"  # valid alphanumeric CNPJ under IN RFB 2.229/2024


# ---------------------------------------------------------------------------
# The premise itself: these patterns really do discriminate against the new format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "predicate"),
    [
        ("numeric regex", lambda v: bool(re.fullmatch(r"\d{14}", v))),
        ("charclass regex", lambda v: bool(re.fullmatch(r"[0-9]{14}", v))),
        ("isdigit", lambda v: v.isdigit()),
    ],
)
def test_flagged_patterns_actually_reject_alphanumeric(name: str, predicate) -> None:
    """A rule is only justified if the pattern it flags really breaks.

    Each accepts the legacy CNPJ and rejects the alphanumeric one, which is
    precisely the regression the scanner exists to find.
    """
    assert predicate(LEGACY) is True, f"{name} should accept a legacy CNPJ"
    assert predicate(ALPHA) is False, f"{name} should reject the alphanumeric CNPJ"


def test_int_cast_destroys_an_alphanumeric_cnpj() -> None:
    assert int(LEGACY) == 11222333000181
    with pytest.raises(ValueError):
        int(ALPHA)


def test_stripping_non_digits_corrupts_an_alphanumeric_cnpj() -> None:
    """The most insidious one: no exception, just a silently wrong value."""
    assert re.sub(r"\D", "", LEGACY) == LEGACY
    corrupted = re.sub(r"\D", "", ALPHA)
    assert corrupted != ALPHA
    assert len(corrupted) < 14


# ---------------------------------------------------------------------------
# Rule metadata
# ---------------------------------------------------------------------------


def test_rules_are_well_formed() -> None:
    ids = [r.id for r in RULES]
    assert len(ids) == len(set(ids)), "rule ids must be unique"
    for rule in RULES:
        assert rule.severity in SEVERITY_ORDER
        assert rule.title and rule.explanation and rule.fix
        assert rule.fix != rule.explanation, f"{rule.id} must say how to fix it"


def test_language_detection() -> None:
    assert language_of("app.py") == "python"
    assert language_of("schema.SQL") == "sql"
    assert language_of("Component.tsx") == "typescript"
    assert language_of("photo.png") is None
    assert language_of("README.md") is None


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _ids(code: str, language: str | None = "python") -> set[str]:
    return {f.rule_id for f in scan_text(code, language=language)}


def test_detects_numeric_only_regex() -> None:
    assert "CNPJ001" in _ids('CNPJ_RE = re.compile(r"^\\d{14}$")')
    assert "CNPJ001" in _ids('if re.match("^[0-9]{14}$", cnpj):')


def test_detects_isdigit_guard() -> None:
    assert "CNPJ003" in _ids("if not cnpj.isdigit():\n    raise ValueError()")


def test_detects_int_cast() -> None:
    assert "CNPJ010" in _ids("record.cnpj_num = int(cnpj)")
    assert "CNPJ010" in _ids("Long.parseLong(cnpj)", language="java")


def test_detects_numeric_sql_column() -> None:
    found = _ids("CREATE TABLE empresa (cnpj BIGINT NOT NULL);", language="sql")
    assert "CNPJ011" in found


@pytest.mark.parametrize(
    "declaration",
    [
        "cnpj = models.BigIntegerField()",
        "cnpj: int = Column(Integer)",
        "cnpj = models.IntegerField(unique=True)",
    ],
)
def test_detects_orm_integer_field(declaration: str) -> None:
    assert "CNPJ012" in _ids(declaration)


def test_detects_non_digit_stripping() -> None:
    assert "CNPJ021" in _ids('cnpj = re.sub(r"\\D", "", raw_cnpj)')


def test_detects_zero_padding() -> None:
    assert "CNPJ013" in _ids("cnpj = cnpj.zfill(14)")


def test_sql_only_rule_does_not_fire_on_python() -> None:
    """CNPJ011 targets DDL; the same words in Python are not a column."""
    code = "cnpj_bigint = 1"
    assert "CNPJ011" not in _ids(code, language="python")


# ---------------------------------------------------------------------------
# Precision -- a noisy scanner gets muted after one run
# ---------------------------------------------------------------------------


def test_clean_modern_code_produces_nothing() -> None:
    code = """
from fiscalkit import CNPJ, is_valid_cnpj

CNPJ_RE = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")

def normalize(value: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", value.upper())

def check(value: str) -> bool:
    return is_valid_cnpj(normalize(value))
"""
    assert scan_text(code, language="python") == []


def test_unrelated_numeric_code_is_not_flagged() -> None:
    """\\d{14} without any CNPJ nearby is somebody else's identifier."""
    code = 'TRACKING_RE = re.compile(r"^\\d{14}$")\nparse(int(order_id))'
    assert _ids(code) == set()


def test_context_window_gates_the_generic_rules() -> None:
    """CNPJ001 needs 'cnpj' nearby; distance beyond the window stops it."""
    near = 'cnpj = form["cnpj"]\nif re.match(r"^\\d{14}$", value):'
    far = 'cnpj = form["cnpj"]\n' + "\n" * 8 + 'if re.match(r"^\\d{14}$", value):'
    assert "CNPJ001" in _ids(near)
    assert "CNPJ001" not in _ids(far)


def test_commented_out_code_is_ignored() -> None:
    for comment in ("# ", "// ", "-- "):
        code = f'{comment}cnpj check: re.match(r"^\\d{{14}}$", cnpj)'
        assert scan_text(code, language="python") == []


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------


def test_scan_directory_reports_and_prunes(tmp_path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "validators.py").write_text(
        'import re\ncnpj = payload["cnpj"]\nif not re.match(r"^\\d{14}$", cnpj):\n    reject()\n',
        encoding="utf-8",
    )
    (tmp_path / "schema.sql").write_text(
        "CREATE TABLE fornecedor (cnpj BIGINT PRIMARY KEY);\n", encoding="utf-8"
    )
    # Dependencies must be pruned, or every scan drowns in third-party noise.
    vendor = tmp_path / "node_modules" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "index.js").write_text("const re = /^\\d{14}$/; // cnpj\n", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    result = scan_path(tmp_path)
    paths = {f.path for f in result.findings}
    assert any("validators.py" in p for p in paths)
    assert any("schema.sql" in p for p in paths)
    assert not any("node_modules" in p for p in paths)
    assert not result.is_clean
    assert result.breaks


def test_scan_result_serializes_and_sorts(tmp_path) -> None:
    import json

    (tmp_path / "m.py").write_text(
        'cnpj = row["cnpj"]\ncnpj = cnpj.zfill(14)\nif not cnpj.isdigit():\n    fail()\n',
        encoding="utf-8",
    )
    result = scan_path(tmp_path)
    payload = result.to_dict()
    json.dumps(payload, ensure_ascii=False)
    severities = [f.severity for f in result.sorted_findings()]
    assert severities == sorted(severities, key=lambda s: SEVERITY_ORDER[s])
    assert payload["pronto_para_2026"] is False


def test_clean_project_is_ready(tmp_path) -> None:
    (tmp_path / "ok.py").write_text(
        "from fiscalkit import is_valid_cnpj\n\ndef check(v): return is_valid_cnpj(v)\n",
        encoding="utf-8",
    )
    result = scan_path(tmp_path)
    assert result.is_clean
    assert result.to_dict()["pronto_para_2026"] is True


def test_unreadable_file_is_skipped_not_fatal(tmp_path) -> None:
    good = tmp_path / "a.py"
    good.write_text("cnpj = 1\n", encoding="utf-8")
    bad = tmp_path / "b.py"
    bad.write_bytes(b"\xff\xfe\x00binary")
    result = scan_path(tmp_path)  # must not raise
    assert result.files_scanned >= 1


def test_scanning_fiscalkit_itself_finds_no_breakage() -> None:
    """The library must not contain the patterns it warns about.

    `rules.py` holds the detection patterns as data, so it is excluded -- a rule
    definition is not a defect.
    """
    from pathlib import Path

    import fiscalkit

    root = Path(fiscalkit.__file__).parent
    offenders = [
        f for f in scan_path(root).findings if f.severity == BREAKS and "rules.py" not in f.path
    ]
    assert offenders == [], f"fiscalkit itself would break: {offenders}"


# ---------------------------------------------------------------------------
# SARIF -- what GitHub code scanning ingests
# ---------------------------------------------------------------------------


def test_sarif_document_is_well_formed(tmp_path) -> None:
    import json

    from fiscalkit.scan.sarif import SARIF_VERSION, to_sarif

    (tmp_path / "a.py").write_text(
        'import re\ncnpj = row["cnpj"]\nif not re.match(r"^\\d{14}$", cnpj):\n    fail()\n',
        encoding="utf-8",
    )
    doc = to_sarif(scan_path(tmp_path))
    json.dumps(doc)  # must survive the transport

    assert doc["version"] == SARIF_VERSION
    assert doc["$schema"].endswith("sarif-schema-2.1.0.json")
    run = doc["runs"][0]

    driver = run["tool"]["driver"]
    assert driver["name"] == "fiscalkit"
    # Every rule is declared, not only the matched ones, so the Security tab can
    # describe a rule even on a scan that reports none of it.
    assert len(driver["rules"]) == len(RULES)

    assert run["results"], "expected at least one result"
    declared = {r["id"] for r in driver["rules"]}
    for result in run["results"]:
        assert result["ruleId"] in declared
        assert result["level"] in {"error", "warning", "note"}
        assert result["message"]["text"]
        region = result["locations"][0]["physicalLocation"]["region"]
        assert region["startLine"] >= 1


def test_sarif_severity_maps_to_github_levels(tmp_path) -> None:
    from fiscalkit.scan.sarif import to_sarif

    (tmp_path / "m.py").write_text(
        'cnpj = row["cnpj"]\ncnpj = int(cnpj)\ncnpj = cnpj.zfill(14)\n', encoding="utf-8"
    )
    levels = {r["ruleId"]: r["level"] for r in to_sarif(scan_path(tmp_path))["runs"][0]["results"]}
    assert levels.get("CNPJ010") == "error"  # breaks
    assert levels.get("CNPJ013") == "warning"  # risky


def test_sarif_uses_relative_forward_slashed_paths(tmp_path) -> None:
    """SARIF requires a relative URI; an absolute Windows path is rejected."""
    from fiscalkit.scan.sarif import to_sarif

    nested = tmp_path / "app" / "db"
    nested.mkdir(parents=True)
    (nested / "m.py").write_text('cnpj = int(row["cnpj"])\n', encoding="utf-8")
    uri = to_sarif(scan_path(tmp_path))["runs"][0]["results"][0]["locations"][0][
        "physicalLocation"
    ]["artifactLocation"]["uri"]
    assert "\\" not in uri
    assert not uri.startswith("/")
    assert uri == "app/db/m.py"


def test_sarif_on_a_clean_project_has_no_results(tmp_path) -> None:
    from fiscalkit.scan.sarif import to_sarif

    (tmp_path / "ok.py").write_text("from fiscalkit import is_valid_cnpj\n", encoding="utf-8")
    doc = to_sarif(scan_path(tmp_path))
    assert doc["runs"][0]["results"] == []
    assert len(doc["runs"][0]["tool"]["driver"]["rules"]) == len(RULES)
