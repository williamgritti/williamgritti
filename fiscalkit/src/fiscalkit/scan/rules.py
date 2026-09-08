"""Detection rules for code that breaks when CNPJs become alphanumeric.

From July 2026, *Instrução Normativa RFB nº 2.229/2024* allows letters in the
first twelve positions of a CNPJ. Validation libraries have already adapted --
``brutils``, ``validate-docbr`` and ``fiscalkit`` all accept the new format. That
is not the migration problem.

The problem is the code around them: a ``^\\d{14}$`` regex guarding an API
boundary, a ``BIGINT`` column, an ``int()`` cast used to strip leading zeros. Each
one silently rejects or corrupts a valid CNPJ, and none of them is fixed by
upgrading a dependency. These rules find that code.

Every rule below is verified against a real alphanumeric CNPJ in the test suite:
each pattern must accept ``11222333000181`` and reject or corrupt
``12ABC34501DE35``. A rule that cannot demonstrate that difference is not a rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["RULES", "Rule", "Severity", "language_of", "rules_for_language"]

Severity = str

#: Certain to break: the pattern provably rejects or corrupts a valid CNPJ.
BREAKS: Severity = "breaks"
#: Probably breaks, but depends on how the value reaches this code.
RISKY: Severity = "risky"
#: Worth a human look; too context-dependent to call automatically.
REVIEW: Severity = "review"

SEVERITY_ORDER = {BREAKS: 0, RISKY: 1, REVIEW: 2}


@dataclass(frozen=True, slots=True)
class Rule:
    """One detectable pattern that does not survive the alphanumeric format."""

    id: str
    title: str
    severity: Severity
    pattern: re.Pattern[str]
    explanation: str
    fix: str
    languages: frozenset[str] | None = None
    #: When true, only report if "cnpj" appears nearby. Keeps precision high for
    #: patterns like ``\\d{14}`` that are meaningless without that context.
    needs_cnpj_context: bool = False
    #: An unambiguous textual rewrite, as ``(search, replace)`` pairs applied to
    #: the offending line. Present only where the correct edit follows from the
    #: pattern alone. A CNPJ cast to an integer has no mechanical fix -- the
    #: surrounding code has to stop treating it as a number -- so that rule
    #: deliberately carries none and ``--fix`` leaves it for a human.
    autofix: tuple[tuple[str, str], ...] | None = None

    @property
    def is_fixable(self) -> bool:
        """Whether this rule carries a mechanical rewrite."""
        return bool(self.autofix)

    def applies_to(self, language: str) -> bool:
        """Whether this rule should run against a file of *language*."""
        return self.languages is None or language in self.languages


def _c(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


#: Extension to language name. Only text formats worth scanning.
EXTENSIONS = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".sql": "sql",
    ".java": "java",
    ".kt": "kotlin",
    ".php": "php",
    ".go": "go",
    ".cs": "csharp",
    ".rb": "ruby",
    ".rs": "rust",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".html": "html",
    ".vue": "javascript",
    # Schema and interface-definition formats. A CNPJ typed as an integer in one
    # of these propagates the defect into every generated client and stub.
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".prisma": "prisma",
    ".avsc": "json",
}


def language_of(filename: str) -> str | None:
    """Return the language for *filename*, or ``None`` if it is not scanned."""
    lowered = filename.lower()
    for ext, lang in EXTENSIONS.items():
        if lowered.endswith(ext):
            return lang
    return None


RULES: tuple[Rule, ...] = (
    # -- Numeric-only validation ------------------------------------------
    Rule(
        id="CNPJ001",
        title="Numeric-only CNPJ regex",
        severity=BREAKS,
        pattern=_c(r"(?:\\d|\[0-9\])\s*\{\s*14\s*\}"),
        needs_cnpj_context=True,
        explanation=(
            "A 14-digit numeric regex rejects every alphanumeric CNPJ. This is the "
            "single most common way a system will start refusing valid documents."
        ),
        fix="Match [0-9A-Z]{12}[0-9]{2} instead: the first twelve positions accept "
        "letters, the two check digits stay numeric.",
        autofix=((r"\d{14}", "[0-9A-Z]{12}[0-9]{2}"), ("[0-9]{14}", "[0-9A-Z]{12}[0-9]{2}")),
    ),
    Rule(
        id="CNPJ002",
        title="Formatted CNPJ mask accepting only digits",
        severity=BREAKS,
        # Anchored on the "/0000" branch group, which is unique to the CNPJ mask.
        # An earlier version matched only the leading \d{2}\.\d{3}, and that
        # fires on version strings, dotted dates, coordinates and -- worst for a
        # Brazilian tool -- the CEP mask \d{2}\.\d{3}-\d{3}, which is in every
        # address form in the country. Context-gated as well, for the same reason.
        pattern=_c(r"(?:\\d|\[0-9\])\s*\{\s*3\s*\}\s*\\?/\s*(?:\\d|\[0-9\])\s*\{\s*4\s*\}"),
        needs_cnpj_context=True,
        explanation=(
            "A 00.000.000/0000-00 mask built from digit classes rejects the "
            "alphanumeric form, which is punctuated identically."
        ),
        fix="Widen the first twelve positions to [0-9A-Z] and keep the final two numeric.",
    ),
    Rule(
        id="CNPJ003",
        title="isdigit / isnumeric check on a CNPJ",
        severity=BREAKS,
        pattern=_c(r"cnpj\w*\s*(?:\.|->|::)\s*(?:isdigit|isnumeric|isdecimal)\s*\(\)"),
        explanation=(
            "isdigit() is False for any CNPJ containing a letter, so this guard "
            "rejects valid documents from July 2026."
        ),
        fix="Validate with a CNPJ validator that knows the 2026 rules, or test "
        "isalnum() plus an explicit check that the last two characters are digits.",
    ),
    Rule(
        id="CNPJ004",
        title="ctype / Number check on a CNPJ",
        severity=BREAKS,
        pattern=_c(
            r"(?<![\w.])(?:ctype_digit|is_numeric|isNaN|Number|parseInt|parseFloat)"
            r"\s*\(\s*[^)]*cnpj"
        ),
        explanation=(
            "Numeric coercion of a CNPJ fails once letters are legal, and the two "
            "ways it fails are not equally survivable. Number() and isNaN() give "
            "NaN, and ctype_digit() gives false, which are loud. parseInt() "
            "truncates at the first letter and returns a plausible number: "
            "parseInt('12ABC34501DE35', 10) is 12. That reaches a database as a "
            "valid-looking value and is discovered much later, if at all."
        ),
        fix="Treat the CNPJ as an opaque string. It is an identifier, never a quantity.",
    ),
    # -- Numeric storage and casting --------------------------------------
    Rule(
        id="CNPJ010",
        title="CNPJ cast to an integer",
        severity=BREAKS,
        # The lookbehind excludes a preceding word character so that "print("
        # does not match on the "int(" inside it. It deliberately allows a
        # preceding dot, because strconv.Atoi, Int32.Parse and Convert.ToInt64
        # are exactly the calls worth finding in Go, C# and Java.
        pattern=_c(
            r"(?:(?<!\w)(?:int|long|bigint|atoi|intval|to_number)\s*\(\s*[^)]{0,40}cnpj"
            r"|(?:Integer\.parseInt|Long\.parseLong|Int32\.Parse|Int64\.Parse"
            r"|Convert\.ToInt32|Convert\.ToInt64|strconv\.(?:Atoi|ParseInt))"
            r"\s*\(\s*[^)]{0,40}cnpj"
            r"|cnpj[^\n]{0,24}\.\s*to_i\b)"
        ),
        explanation=(
            "Casting to an integer throws or truncates on an alphanumeric CNPJ, and "
            "silently discards leading zeros even today."
        ),
        fix="Keep the CNPJ as a string end to end.",
    ),
    Rule(
        id="CNPJ011",
        title="CNPJ column declared as a numeric type",
        severity=BREAKS,
        pattern=_c(
            r"cnpj\w*\s+(?:big\s*int|bigint|int(?:eger)?|numeric|decimal|number|bigserial|long)\b"
        ),
        languages=frozenset({"sql"}),
        explanation=(
            "PostgreSQL, MySQL and SQLite STRICT tables reject an alphanumeric CNPJ "
            "outright. SQLite's default type affinity is worse: it accepts the value "
            "and stores it as TEXT in a column declared BIGINT, leaving legacy rows "
            "as integers and new ones as text in the same column, so the failure "
            "surfaces later on a join, an ORDER BY or a comparison. Either way this "
            "is a schema migration, which needs the longest lead time of anything here."
        ),
        fix="Migrate to CHAR(14) or VARCHAR(14). Plan for a backfill and for every "
        "foreign key that references this column.",
        autofix=(
            ("BIGINT", "CHAR(14)"),
            ("bigint", "CHAR(14)"),
            ("NUMERIC(14)", "CHAR(14)"),
            ("DECIMAL(14,0)", "CHAR(14)"),
        ),
    ),
    Rule(
        id="CNPJ012",
        title="CNPJ mapped to an integer field in an ORM",
        severity=BREAKS,
        # Two shapes: `cnpj = IntegerField()` (Python/ORM, name first) and
        # `private BigInteger cnpj;` or `public long Cnpj { get; set; }`
        # (Java/C#, type first). Only the first was matched before.
        pattern=_c(
            r"(?:cnpj\w*\s*[:=]\s*(?:models\.)?(?:Big)?"
            r"(?:Integer|Int|Number|Numeric|Decimal|Long)(?:Field|Column)?\b"
            r"|(?<!\w)(?:big)?(?:integer|int|int32|int64|long|number|numeric|decimal"
            r"|biginteger|bigdecimal)\s+cnpj\w*\s*[;={,)])"
        ),
        explanation="The ORM will generate a numeric column that cannot hold letters.",
        fix="Use a character field of length 14.",
        autofix=(
            ("models.BigIntegerField(", "models.CharField(max_length=14, "),
            ("models.IntegerField(", "models.CharField(max_length=14, "),
        ),
    ),
    Rule(
        id="CNPJ013",
        title="Zero-padding a CNPJ back to 14 characters",
        severity=RISKY,
        # Receiver form (cnpj.zfill), chained form (String(x.cnpj).padStart)
        # and argument form (str_pad($cnpj, 14, ...)), which PHP uses.
        pattern=_c(
            r"(?:cnpj[^\n]{0,24}(?:\.|->|::)\s*(?:zfill|rjust|padStart|str_pad|PadLeft|padleft)\s*\("
            r"|(?:zfill|rjust|padStart|str_pad|PadLeft)\s*\(\s*[^)]{0,30}cnpj)"
        ),
        explanation=(
            "Zero-padding exists to repair a CNPJ that was stored as a number. The "
            "padding itself is harmless; what it implies about the storage is not."
        ),
        fix="Find where the leading zeros were lost. That is the actual defect.",
    ),
    # -- Length and formatting assumptions --------------------------------
    Rule(
        id="CNPJ020",
        title="CNPJ compared against a numeric literal",
        severity=RISKY,
        pattern=_c(r"cnpj\w*\s*(?:==|!=|===|!==|<>)\s*\d{6,}"),
        explanation="Comparing a CNPJ to a bare number means it is being held as one.",
        fix="Compare strings, and normalize case before comparing.",
    ),
    Rule(
        id="CNPJ021",
        title="CNPJ normalized by stripping non-digits",
        severity=BREAKS,
        pattern=_c(
            r"(?:replace|sub|gsub|preg_replace|RegExp)\s*\(\s*[^)]{0,30}"
            r"(?:\[\^0-9\]|\[\^\\d\]|\\D)"
        ),
        needs_cnpj_context=True,
        explanation=(
            "Stripping everything that is not a digit deletes the letters out of an "
            "alphanumeric CNPJ, producing a shorter value that then fails validation."
        ),
        fix="Strip only punctuation: remove [^0-9A-Z] after upper-casing.",
        autofix=(
            ("[^0-9]", "[^0-9A-Z]"),
            (r"[^\d]", "[^0-9A-Z]"),
            (r"\D", "[^0-9A-Z]"),
        ),
    ),
    Rule(
        id="CNPJ022",
        title="CNPJ check digits computed without the ASCII-48 mapping",
        severity=REVIEW,
        pattern=_c(r"(?:int|ord|charCodeAt|Integer\.parseInt)\s*\(\s*\w*\s*\[\s*i\s*\]"),
        needs_cnpj_context=True,
        explanation=(
            "A hand-rolled check-digit loop that converts each character with int() "
            "rather than ord(c) - 48 cannot score letters."
        ),
        fix="Map each character with ord(c) - 48, which reproduces the legacy numeric "
        "result exactly, so one code path serves both formats.",
    ),
    Rule(
        id="CNPJ014",
        title="CNPJ typed as an integer in a schema or API spec",
        severity=BREAKS,
        # OpenAPI, JSON Schema and Avro put the type on its own line under the
        # field name, so this is keyed on the type and gated on nearby context
        # rather than trying to match both on one line.
        pattern=_c(r"[\"']?type[\"']?\s*[:=]\s*[\"']?(?:integer|number|int32|int64|long)\b"),
        needs_cnpj_context=True,
        explanation=(
            "A CNPJ declared as an integer in a specification does not stay in the "
            "specification: every generated client, server stub and validator "
            "inherits it, so one line here becomes the same defect in several "
            "languages at once."
        ),
        fix="Type it as a string with a maxLength of 14. Keep any pattern "
        "constraint alphanumeric: ^[0-9A-Z]{12}[0-9]{2}$.",
    ),
    Rule(
        id="CNPJ015",
        title="CNPJ declared as an integer field without a separator",
        severity=BREAKS,
        # Prisma, Protobuf IDL and Go struct tags write `cnpj Int` with only
        # whitespace between name and type, which the assignment forms miss.
        # The trailing exclusion keeps prose out. A declaration is followed by end
        # of line, an attribute, or punctuation; `print("cnpj integer")` is
        # followed by a quote, and is a sentence rather than a field.
        pattern=_c(
            r"(?<![\w.])cnpj\w*\s+(?:big)?int(?:eger|32|64)?\b"
            r"(?!\s*\()(?!\s*[\"'`])(?=\s*(?:$|[@?!\[\],;:=)]|\w))"
        ),
        # Scoped to the languages that actually write `cnpj Int` with only
        # whitespace between name and type. SQL is deliberately excluded: a
        # numeric column there is CNPJ011's, and matching both reported the same
        # line twice, which is noise a reader has to reconcile.
        languages=frozenset({"prisma", "graphql", "go"}),
        explanation=(
            "An integer field type carries into the generated schema and the "
            "database column behind it."
        ),
        fix="Declare it as a string or varchar of length 14.",
    ),
    Rule(
        id="CNPJ023",
        title="Fixed-width numeric CNPJ in a file layout",
        severity=REVIEW,
        pattern=_c(r"cnpj\w*\s*[:=,]\s*(?:9{6,}|0{6,})"),
        explanation=(
            "COBOL-style PIC clauses and fixed-width layouts that declare the CNPJ as "
            "numeric will not carry letters through."
        ),
        fix="Redeclare the field as alphanumeric in the layout and in every consumer.",
    ),
)


def rules_for_language(language: str) -> tuple[Rule, ...]:
    """Return the rules that apply to *language*."""
    return tuple(rule for rule in RULES if rule.applies_to(language))
