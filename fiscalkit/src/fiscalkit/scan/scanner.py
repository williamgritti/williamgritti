"""Walk a project and report code that breaks on alphanumeric CNPJs.

Precision is the whole design constraint. A scanner that reports a hundred
maybes gets muted after the first run, so context-dependent rules only fire when
``cnpj`` appears nearby, comment-only lines are skipped, and every finding names
the fix rather than only the problem.

One deliberate consequence: a docstring or string literal that quotes a pattern
near the word ``cnpj`` is reported, because the scanner reads lines rather than
parsing each language. Documentation describing a numeric-only CNPJ rule is
usually worth the same look as the code implementing one, so this is left as a
finding rather than suppressed. ``fiscalkit`` reports its own rules module for
exactly this reason.
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

#: A line this long means a bundled or minified artifact. A finding in one is
#: unactionable: it reports "line 1" of a file the author never edits, and the
#: excerpt is a meaningless slice of a single enormous line. The original source
#: is elsewhere and is what should be fixed.
MAX_LINE_LENGTH = 2_000

#: How many lines either side count as "nearby" for context-dependent rules.
#:
#: Two lines was too tight for real code. A helper that normalizes a CNPJ is
#: routinely a few lines from the nearest mention of one -- the function is named
#: `normalizar`, the caller passes `cnpj`, and the module constant sits above the
#: import block -- so the most dangerous rule in the set, the silent
#: `re.sub(r"\D", "", ...)` corruption, was missed in exactly the layout it
#: targets.
#:
#: Chosen by measurement rather than taste. Across 3,225 third-party files, 41
#: files of brutils and validate-docbr, and 240 files of Brazilian npm packages,
#: any window from 4 to 15 finds the helper and reports nothing else. Cost only
#: appears beyond that: at 40 the npm corpus produces two findings. Eight covers
#: a small function and its signature with margin on both sides of the measured
#: safe range.
CONTEXT_LINES = 8

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
    """Everything one scan found, plus what it looked at and what it did not."""

    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    files_skipped: int = 0
    #: Files that parsed but were set aside as bundled or minified output.
    files_minified: int = 0
    #: Scannable files that were never read because they sit in a pruned
    #: directory, keyed by the directory name responsible.
    pruned: dict[str, int] = field(default_factory=dict)

    @property
    def files_pruned(self) -> int:
        """How many scannable files a pruned directory hid from this scan."""
        return sum(self.pruned.values())

    @property
    def breaks(self) -> list[Finding]:
        """Findings certain to reject or corrupt a valid CNPJ."""
        return [f for f in self.findings if f.severity == "breaks"]

    @property
    def is_clean(self) -> bool:
        """Whether files were scanned and nothing was found.

        A scan that examined no files is not clean, it is uninformative. Saying
        otherwise turns "I could not look" into "you are ready", which is the
        one answer a compliance tool must never give by accident.
        """
        return self.files_scanned > 0 and not self.findings

    @property
    def scanned_nothing(self) -> bool:
        """Whether no file was examined at all, so the result means nothing."""
        return self.files_scanned == 0

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
            "nada_analisado": self.scanned_nothing,
            "arquivos_minificados": self.files_minified,
            "arquivos_podados": self.files_pruned,
            "diretorios_podados": dict(sorted(self.pruned.items())),
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


def _walk(root: Path, *, prune: bool, pruned: dict[str, int]) -> Iterator[Path]:
    """Yield scannable files under *root*, recording what pruning hid.

    Pruning is applied only to path components *below* *root*, never to the
    components of *root* itself. Otherwise pointing the scanner at a directory
    that happens to sit inside ``site-packages`` or ``build`` skips every file
    and reports a clean project -- a false all-clear, which is the worst answer
    a compliance scanner can give. If the caller named the directory explicitly,
    they meant it.

    Pruning is never silent either. A published npm package keeps its only copy
    of the code in ``dist``, so scanning one prunes every file and would
    otherwise report the package ready without having read a line of it. What
    was hidden is counted into *pruned* so the caller can say so, and ``prune``
    turns the behaviour off entirely.
    """
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:  # pragma: no cover - rglob results are under root
            relative = path
        if prune:
            hidden_by = next((part for part in relative.parts if part in SKIP_DIRS), None)
            if hidden_by is not None:
                # Only count files this scan would otherwise have read.
                if language_of(path.name) is not None:
                    pruned[hidden_by] = pruned.get(hidden_by, 0) + 1
                continue
        yield path


def scan_path(root: str | Path, *, prune: bool = True) -> ScanResult:
    """Scan every recognized source file under *root*.

    Args:
        root: File or directory to scan.
        prune: Skip dependency and build directories. Leave on for a source
            repository; turn it off for a published artifact whose only copy of
            the code lives in a directory this would otherwise skip.

    Unreadable and oversized files are counted as skipped rather than raising, so
    one unreadable file cannot abort a scan of a large repository.
    """
    result = ScanResult()
    base = Path(root)
    # Paths are reported relative to the directory being scanned. When the target
    # is a single file, `path.relative_to(base)` is "." -- a path relative to
    # itself names nothing -- so anchor on its parent and report the file's own
    # name, exactly as a scan of that directory would. The "." leaked further than
    # the report: `--fix` resolved it back to the directory, the read failed, and
    # the CLI told the user no automatic fix was available for a finding that has
    # one. A wrong answer delivered quietly, which is the thing this tool exists
    # to find in other people's code.
    anchor = base.parent if base.is_file() else base
    for path in _walk(base, prune=prune, pruned=result.pruned):
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
        # Reported, never silent, for the same reason pruning is.
        if any(len(line) > MAX_LINE_LENGTH for line in text.splitlines()):
            result.files_minified += 1
            continue
        display = str(path.relative_to(anchor))
        result.findings.extend(scan_text(text, path=display, language=language))
        result.files_scanned += 1
    return result
