"""Walk a project and report code that breaks on alphanumeric CNPJs.

Precision is the whole design constraint. A scanner that reports a hundred
maybes gets muted after the first run, so context-dependent rules only fire when
``cnpj`` appears nearby, comment-only lines are skipped, and every finding names
the fix rather than only the problem.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .rules import RULES, SEVERITY_ORDER, Rule, language_of

__all__ = ["Finding", "ScanResult", "scan_path", "scan_text"]

#: Directories never worth scanning: dependencies, build output, VCS metadata.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "vendor",
        "venv",
        ".venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
        "target",
        "bin",
        "obj",
        ".next",
        ".nuxt",
        "coverage",
        "site-packages",
        ".idea",
        ".vscode",
        "migrations_backup",
    }
)

#: Files above this size are almost certainly data or minified bundles.
MAX_FILE_BYTES = 2_000_000

#: How many lines either side count as "nearby" for context-dependent rules.
CONTEXT_LINES = 2

_CNPJ_MENTION = re.compile(r"cnpj", re.IGNORECASE)

# Line-comment prefixes by language. A commented-out regex is not live code.
_COMMENT_PREFIXES = ("#", "//", "--", "*", "/*", "<!--")


@dataclass(frozen=True, slots=True)
class Finding:
    """One rule match at one location."""

    rule_id: str
    title: str
    severity: str
    path: str
    line: int
    excerpt: str
    explanation: str
    fix: str

    def to_dict(self) -> dict[str, object]:
        """Render as a JSON-friendly mapping."""
        return {
            "regra": self.rule_id,
            "titulo": self.title,
            "severidade": self.severity,
            "arquivo": self.path,
            "linha": self.line,
            "trecho": self.excerpt,
            "explicacao": self.explanation,
            "correcao": self.fix,
        }


@dataclass(slots=True)
class ScanResult:
    """Everything one scan found, plus what it looked at."""

    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    files_skipped: int = 0

    @property
    def breaks(self) -> list[Finding]:
        """Findings certain to reject or corrupt a valid CNPJ."""
        return [f for f in self.findings if f.severity == "breaks"]

    @property
    def is_clean(self) -> bool:
        """Whether nothing at all was found."""
        return not self.findings

    def sorted_findings(self) -> list[Finding]:
        """Findings ordered by severity, then by location."""
        return sorted(
            self.findings,
            key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.path, f.line),
        )

    def counts(self) -> dict[str, int]:
        """Number of findings per severity."""
        out: dict[str, int] = {}
        for finding in self.findings:
            out[finding.severity] = out.get(finding.severity, 0) + 1
        return out

    def to_dict(self) -> dict[str, object]:
        """Render the whole result as a JSON-friendly mapping."""
        return {
            "arquivos_analisados": self.files_scanned,
            "arquivos_ignorados": self.files_skipped,
            "total": len(self.findings),
            "por_severidade": self.counts(),
            "pronto_para_2026": self.is_clean,
            "ocorrencias": [f.to_dict() for f in self.sorted_findings()],
        }


def _is_comment(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(_COMMENT_PREFIXES)


def _has_cnpj_context(lines: list[str], index: int) -> bool:
    """Whether ``cnpj`` appears within :data:`CONTEXT_LINES` of *index*."""
    lo = max(0, index - CONTEXT_LINES)
    hi = min(len(lines), index + CONTEXT_LINES + 1)
    return any(_CNPJ_MENTION.search(lines[i]) for i in range(lo, hi))


def scan_text(text: str, *, path: str = "<string>", language: str | None = None) -> list[Finding]:
    """Scan *text* and return its findings.

    Args:
        text: The source to scan.
        path: Label used in the findings.
        language: Language name; when ``None`` every language-agnostic rule runs.
    """
    lines = text.splitlines()
    applicable: tuple[Rule, ...] = tuple(
        r for r in RULES if language is None or r.applies_to(language)
    )
    findings: list[Finding] = []
    for index, line in enumerate(lines):
        if _is_comment(line):
            continue
        for rule in applicable:
            if not rule.pattern.search(line):
                continue
            if rule.needs_cnpj_context and not _has_cnpj_context(lines, index):
                continue
            findings.append(
                Finding(
                    rule_id=rule.id,
                    title=rule.title,
                    severity=rule.severity,
                    path=path,
                    line=index + 1,
                    excerpt=line.strip()[:160],
                    explanation=rule.explanation,
                    fix=rule.fix,
                )
            )
    return findings


def _walk(root: Path) -> Iterator[Path]:
    """Yield scannable files under *root*, pruning dependency directories."""
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def scan_path(root: str | Path) -> ScanResult:
    """Scan every recognized source file under *root*.

    Unreadable and oversized files are counted as skipped rather than raising, so
    one unreadable file cannot abort a scan of a large repository.
    """
    result = ScanResult()
    base = Path(root)
    for path in _walk(base):
        language = language_of(path.name)
        if language is None:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                result.files_skipped += 1
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            result.files_skipped += 1
            continue
        try:
            display = str(path.relative_to(base))
        except ValueError:  # pragma: no cover - root is a file
            display = str(path)
        result.findings.extend(scan_text(text, path=display, language=language))
        result.files_scanned += 1
    return result
