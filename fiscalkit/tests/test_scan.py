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


# ---------------------------------------------------------------------------
# Behaviour derived from testing against real Brazilian CNPJ libraries
# ---------------------------------------------------------------------------


def test_correct_2026_isdigit_pattern_is_not_flagged() -> None:
    """`cnpj[12:].isdigit()` is right; `cnpj.isdigit()` is wrong.

    Under IN RFB 2.229/2024 the two check digits stay numeric while the first
    twelve positions may hold letters, so asserting the *slice* is numeric is
    exactly correct. `brutils` does precisely this, and flagging it would make
    the scanner cry wolf on the reference implementation.
    """
    assert "CNPJ003" not in _ids("if not cnpj[12:].isdigit():\n    return False")
    assert "CNPJ003" not in _ids("valid = cnpj[12:14].isdigit()")
    # The unsliced form is the actual defect and must still be caught.
    assert "CNPJ003" in _ids("if not cnpj.isdigit():\n    return False")


def test_no_false_positives_on_a_correct_implementation() -> None:
    """A faithful 2026-ready validator must scan completely clean."""
    reference = """
def is_valid(cnpj: str) -> bool:
    if len(cnpj) != 14:
        return False
    if not cnpj[12:].isdigit():
        return False
    return _check_digits(cnpj) == cnpj[12:]


def _value(char: str) -> int:
    return ord(char) - 48


def remove_symbols(dirty: str) -> str:
    return "".join(c for c in dirty.upper() if c.isalnum())
"""
    assert scan_text(reference, language="python") == []


def test_directory_named_in_skip_dirs_is_still_scanned_when_given_explicitly(
    tmp_path,
) -> None:
    """Pruning must apply below the root, never to the root's own path.

    Pointing the scanner at something inside `site-packages` or `build` used to
    skip every file and report the project ready -- a false all-clear, the worst
    answer a compliance tool can give.
    """
    target = tmp_path / "site-packages" / "mylib"
    target.mkdir(parents=True)
    (target / "m.py").write_text('cnpj = int(row["cnpj"])\n', encoding="utf-8")

    explicit = scan_path(target)
    assert explicit.files_scanned == 1
    assert explicit.breaks

    # From above it, the same directory is correctly treated as a dependency.
    from_parent = scan_path(tmp_path)
    assert from_parent.files_scanned == 0


def test_empty_scan_is_not_reported_as_ready(tmp_path) -> None:
    """ "I could not look" must never render as "you are ready"."""
    (tmp_path / "notes.md").write_text("no source here\n", encoding="utf-8")
    result = scan_path(tmp_path)
    assert result.files_scanned == 0
    assert result.scanned_nothing is True
    assert result.is_clean is False
    assert result.to_dict()["pronto_para_2026"] is False
    assert result.to_dict()["nada_analisado"] is True


def test_scanned_files_with_no_findings_are_clean(tmp_path) -> None:
    (tmp_path / "ok.py").write_text("from fiscalkit import is_valid_cnpj\n", encoding="utf-8")
    result = scan_path(tmp_path)
    assert result.files_scanned == 1
    assert result.scanned_nothing is False
    assert result.is_clean is True


# ---------------------------------------------------------------------------
# CNPJ002 must not fire on the other dotted-numeric masks in Brazilian code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "label"),
    [
        ('VERSION_RE = re.compile(r"^\\d{2}\\.\\d{3}$")', "version string"),
        ('DATE_RE = re.compile(r"\\d{2}\\.\\d{3}\\.\\d{4}")', "dotted date"),
        ('COORD = r"[0-9]{2}\\.[0-9]{3}"', "coordinates"),
        ('CEP_RE = re.compile(r"\\d{2}\\.\\d{3}-\\d{3}")', "CEP"),
        ('CPF_RE = re.compile(r"\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}")', "CPF"),
        ('ROUTE = r"\\d{3}/\\d{4}"', "route id with no CNPJ nearby"),
    ],
)
def test_cnpj_mask_rule_ignores_other_masks(code: str, label: str) -> None:
    """CEP is the one that matters most: it is in every Brazilian address form.

    An earlier version of this rule matched only the leading ``\\d{2}\\.\\d{3}``
    and fired on all of these. A Brazilian tool that cries wolf on a CEP regex
    gets uninstalled the same afternoon.
    """
    assert "CNPJ002" not in _ids(code), f"false positive on {label}"


@pytest.mark.parametrize(
    "code",
    [
        'cnpj_mask = re.compile(r"^\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2}$")',
        'CNPJ = r"[0-9]{2}\\.[0-9]{3}\\.[0-9]{3}/[0-9]{4}-[0-9]{2}"',
    ],
)
def test_cnpj_mask_rule_still_catches_the_real_thing(code: str) -> None:
    """The /0000 branch group is what distinguishes a CNPJ mask from the rest."""
    assert "CNPJ002" in _ids(code)


# ---------------------------------------------------------------------------
# The multi-language claim, verified against idiomatic code in each
# ---------------------------------------------------------------------------

LANGUAGE_CASES = [
    ("javascript", "const CNPJ_RE = /^\\d{14}$/;\nconst cnpj = row.cnpj;", "numeric regex"),
    ("javascript", "const cnpj = parseInt(row.cnpj, 10);", "parseInt"),
    ("javascript", 'const cnpj = String(row.cnpj).padStart(14, "0");', "chained padStart"),
    ("javascript", 'const cnpj = raw.replace(/\\D/g, "");', "strip non-digits"),
    ("typescript", "const cnpj: number = Number(payload.cnpj);", "Number()"),
    ("php", '$cnpj = preg_replace("/[^0-9]/", "", $raw_cnpj);', "preg_replace"),
    ("php", "if (!ctype_digit($cnpj)) { throw new Exception(); }", "ctype_digit"),
    ("php", '$cnpj = str_pad($cnpj, 14, "0", STR_PAD_LEFT);', "str_pad as argument"),
    ("php", '$cnpj = intval($row["cnpj"]);', "intval"),
    ("go", "cnpj, err := strconv.Atoi(row.CNPJ)", "strconv.Atoi"),
    ("csharp", "int cnpj = Int32.Parse(row.Cnpj);", "Int32.Parse"),
    ("csharp", "public long Cnpj { get; set; }", "long property"),
    ("csharp", "cnpj = cnpj.PadLeft(14, '0');", "PadLeft"),
    ("ruby", "cnpj = row[:cnpj].to_i", "to_i after subscript"),
    ("ruby", 'cnpj = raw.gsub(/\\D/, "")', "gsub strip"),
    ("java", "Long cnpj = Long.parseLong(row.getCnpj());", "parseLong"),
    ("java", "private BigInteger cnpj;", "type-first field declaration"),
    ("sql", "ALTER TABLE empresa ADD COLUMN cnpj NUMERIC(14);", "numeric column"),
    ("sql", "cnpj DECIMAL(14,0) NOT NULL", "decimal column"),
]


@pytest.mark.parametrize(("language", "code", "label"), LANGUAGE_CASES)
def test_idiomatic_breakage_is_caught_in_every_claimed_language(
    language: str, code: str, label: str
) -> None:
    """The README claims eight languages; each must fire on idiomatic code.

    The rules were written Python-first and originally missed eight of these --
    Go's `strconv.Atoi`, C#'s `Int32.Parse` and `long Cnpj { get; set; }`,
    Ruby's `row[:cnpj].to_i`, PHP's `intval` and argument-position `str_pad`,
    Java's type-first field declaration, and chained `padStart`. A documented
    claim that the code does not honour is the same defect as a wrong one.
    """
    assert scan_text(code, language=language), f"{language}: missed {label}"


# ---------------------------------------------------------------------------
# Precision after widening those rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "label"),
    [
        ('print("CNPJ alfanumerico encontrado")', "print() with CNPJ in a string"),
        ("sprint(cnpj)", "sprint"),
        ("PhoneNumber(cnpj)", "PhoneNumber"),
        ('total = int(row["quantity"])', "unrelated int cast"),
        ("name = str_pad($nome, 20)", "unrelated str_pad"),
        ("id = row[:order_id].to_i", "unrelated to_i"),
        ("private BigInteger valorTotal;", "unrelated BigInteger field"),
        ("public long OrderId { get; set; }", "unrelated long property"),
        ("n, _ := strconv.Atoi(row.Quantity)", "unrelated Atoi"),
        ("if not cnpj[12:].isdigit(): return False", "the correct 2026 slice check"),
    ],
)
def test_widened_rules_did_not_lose_precision(code: str, label: str) -> None:
    """Widening for other languages must not start flagging unrelated code."""
    assert scan_text(code, language="python") == [], f"false positive on {label}"


def test_prose_quoting_a_pattern_is_reported() -> None:
    """A docstring describing a numeric CNPJ rule is reported, by design.

    The scanner reads lines rather than parsing each of eight languages, so it
    cannot distinguish a regex in code from one quoted in a docstring. Rather
    than suppress the class, this is left as a finding: documentation that
    describes a numeric-only CNPJ rule usually deserves the same review as code
    that implements one. `fiscalkit`'s own rules module reports for this reason.
    """
    docstring = '"""Finds a ^\\d{14}$ regex used to validate a cnpj."""'
    assert "CNPJ001" in _ids(docstring)
    # A `#` comment is still skipped -- that is a separate, deliberate rule.
    assert scan_text("# a ^\\d{14}$ regex for cnpj", language="python") == []


# ---------------------------------------------------------------------------
# Pruning and bundled output must be visible, never silent
# ---------------------------------------------------------------------------


def test_pruning_is_counted_and_reported(tmp_path) -> None:
    """A published npm package keeps its only copy of the code in `dist`.

    Scanning one used to prune every file and report the package ready without
    having read a line of it -- the same false all-clear as the site-packages
    bug, reached by a different route. What pruning hides is now counted.
    """
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "bundle.js").write_text("const cnpj = parseInt(row.cnpj, 10);\n", encoding="utf-8")
    (tmp_path / "index.js").write_text("export {};\n", encoding="utf-8")

    pruned = scan_path(tmp_path)
    assert pruned.files_pruned == 1
    assert pruned.pruned == {"dist": 1}
    assert pruned.to_dict()["arquivos_podados"] == 1

    # Turning pruning off reaches the code and finds the defect.
    everything = scan_path(tmp_path, prune=False)
    assert everything.files_pruned == 0
    assert everything.breaks


def test_pruning_only_counts_files_it_would_have_read(tmp_path) -> None:
    """A PNG inside dist/ is not a file the scan was ever going to open."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (dist / "app.js").write_text("var x = 1;\n", encoding="utf-8")
    assert scan_path(tmp_path).files_pruned == 1


def test_minified_bundles_are_set_aside_and_counted(tmp_path) -> None:
    """A finding on line 1 of a minified bundle is unactionable.

    The excerpt is a meaningless slice of one enormous line, and the fix belongs
    in the original source, which is elsewhere. Set aside, but counted, because
    silently ignoring files is the failure mode this project keeps hitting.
    """
    (tmp_path / "app.min.js").write_text(
        "var a=1;/*" + "z" * 3000 + "*/ var cnpj=parseInt(x.cnpj);\n", encoding="utf-8"
    )
    (tmp_path / "src.js").write_text("const cnpj = parseInt(row.cnpj, 10);\n", encoding="utf-8")

    result = scan_path(tmp_path)
    assert result.files_minified == 1
    assert result.files_scanned == 1
    assert result.to_dict()["arquivos_minificados"] == 1
    # The real source is still reported.
    assert result.breaks
    assert all("min.js" not in f.path for f in result.findings)


def test_ordinary_long_lines_are_still_scanned(tmp_path) -> None:
    """The threshold must not exclude merely verbose real code."""
    line = 'cnpj = int(row["cnpj"])  # ' + "x" * 500 + "\n"
    (tmp_path / "verbose.py").write_text(line, encoding="utf-8")
    result = scan_path(tmp_path)
    assert result.files_minified == 0
    assert result.breaks
