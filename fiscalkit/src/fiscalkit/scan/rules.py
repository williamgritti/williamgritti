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
        explanation=("Numeric coercion of a CNPJ yields NaN or false once letters are legal."),
        fix="Treat the CNPJ as an opaque string. It is an identifier, never a quantity.",
    ),
    # -- Numeric storage and casting --------------------------------------
    Rule(
        id="CNPJ010",
        title="CNPJ cast to an integer",
        severity=BREAKS,
        # The leading lookbehind matters: without it "print(" contains "int(" and
        # every log line mentioning a CNPJ is reported as an integer cast.
        pattern=_c(
            r"(?:(?<![\w.])(?:int|long|bigint|atoi)\s*\(\s*[^)]{0,40}cnpj"
            r"|(?:Integer\.parseInt|Long\.parseLong)\s*\(\s*[^)]{0,40}cnpj"
            r"|cnpj\w*\s*\.\s*to_i\b)"
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
            "An integer column cannot store a CNPJ containing letters at all. This "
            "is a schema migration, so it needs the longest lead time of anything here."
        ),
        fix="Migrate to CHAR(14) or VARCHAR(14). Plan for a backfill and for every "
        "foreign key that references this column.",
    ),
    Rule(
        id="CNPJ012",
        title="CNPJ mapped to an integer field in an ORM",
        severity=BREAKS,
        pattern=_c(
            r"cnpj\w*\s*[:=]\s*(?:models\.)?(?:Big)?(?:Integer|Int|Number|Numeric|Decimal|Long)"
            r"(?:Field|Column)?\b"
        ),
        explanation="The ORM will generate a numeric column that cannot hold letters.",
        fix="Use a character field of length 14.",
    ),
    Rule(
        id="CNPJ013",
        title="Zero-padding a CNPJ back to 14 characters",
        severity=RISKY,
        pattern=_c(r"cnpj\w*\s*(?:\.|->|::)\s*(?:zfill|rjust|padStart|str_pad|PadLeft)\s*\("),
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
