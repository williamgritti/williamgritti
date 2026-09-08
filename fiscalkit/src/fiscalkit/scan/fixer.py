"""Turn findings into patches, for the rules whose correct edit is unambiguous.

A scanner that reports a problem leaves the work with the reader. Against a
statutory deadline, a patch is worth considerably more than a description, so the
rules whose fix follows mechanically from the pattern carry the rewrite with them
and this module applies it.

Deliberately conservative. Only four of the fourteen rules are fixable, and the
ones left out are left out on purpose: `int(cnpj)` cannot be repaired by editing
that line, because the surrounding code has to stop treating a CNPJ as a number,
and a tool that guessed at it would produce a plausible diff that silently
changed behaviour. Those stay reported and unfixed.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from .rules import RULES
from .scanner import Finding

__all__ = ["ApplyResult", "FilePatch", "apply_patches", "build_patches", "unified_diff"]

_BY_ID = {rule.id: rule for rule in RULES}


@dataclass(frozen=True, slots=True)
class FilePatch:
    """The proposed new content of one file, with the findings it resolves."""

    path: Path
    original: str
    patched: str
    rule_ids: tuple[str, ...]

    @property
    def changed(self) -> bool:
        """Whether the rewrite actually altered anything."""
        return self.original != self.patched


def _rewrite_line(line: str, rule_id: str) -> str:
    """Apply one rule's rewrites to *line*, leaving it alone if none match."""
    rule = _BY_ID.get(rule_id)
    if rule is None or not rule.autofix:
        return line
    for search, replace in rule.autofix:
        if search in line:
            line = line.replace(search, replace)
    return line


def _read_preserving_newlines(path: Path) -> str:
    """Read *path* without translating its line endings.

    ``Path.read_text`` opens in universal-newline mode, which turns every CRLF
    into a bare LF in the returned string. Writing that string back rewrites the
    entire file, so a one-line fix in a Windows-authored source tree arrived as a
    diff touching every line -- which is exactly the reviewability ``--fix``
    exists to provide. Brazilian enterprise codebases are full of CRLF, so this
    is the common case here, not the exotic one.

    ``newline=""`` leaves "\r\n" in the text, where ``splitlines(keepends=True)``
    keeps it attached to its line and the rewrite carries it through untouched.
    """
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def build_patches(findings: list[Finding], root: Path) -> list[FilePatch]:
    """Compute a patch per file from the fixable findings.

    Findings whose rule has no mechanical rewrite are ignored here; they remain
    in the report for a human to act on.

    Files are read fresh rather than reconstructed from the excerpts, so a patch
    is always against the file as it is now.
    """
    by_file: dict[str, list[Finding]] = {}
    for finding in findings:
        rule = _BY_ID.get(finding.rule_id)
        if rule is not None and rule.is_fixable:
            by_file.setdefault(finding.path, []).append(finding)

    patches: list[FilePatch] = []
    for relative, file_findings in sorted(by_file.items()):
        path = root / relative if not Path(relative).is_absolute() else Path(relative)
        try:
            original = _read_preserving_newlines(path)
        except OSError:
            continue
        lines = original.splitlines(keepends=True)
        applied: list[str] = []
        for finding in file_findings:
            index = finding.line - 1
            if not 0 <= index < len(lines):
                continue
            rewritten = _rewrite_line(lines[index], finding.rule_id)
            if rewritten != lines[index]:
                lines[index] = rewritten
                applied.append(finding.rule_id)
        patched = "".join(lines)
        if patched != original:
            patches.append(
                FilePatch(
                    path=path,
                    original=original,
                    patched=patched,
                    rule_ids=tuple(dict.fromkeys(applied)),
                )
            )
    return patches


def unified_diff(patches: list[FilePatch], root: Path) -> str:
    """Render *patches* as a unified diff, in the shape ``git apply`` accepts."""
    chunks: list[str] = []
    for patch in patches:
        try:
            label = str(patch.path.relative_to(root))
        except ValueError:  # pragma: no cover - path outside the scanned root
            label = str(patch.path)
        chunks.extend(
            difflib.unified_diff(
                patch.original.splitlines(keepends=True),
                patch.patched.splitlines(keepends=True),
                fromfile=f"a/{label}",
                tofile=f"b/{label}",
            )
        )
    return "".join(chunks)


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """What ``apply_patches`` managed to write, and what it could not."""

    written: list[Path]
    #: Path and the reason it could not be written, in the order encountered.
    failed: list[tuple[Path, str]]

    @property
    def ok(self) -> bool:
        """Whether every patch was written."""
        return not self.failed


def apply_patches(patches: list[FilePatch]) -> ApplyResult:
    """Write each patch to disk and report what was written and what was not.

    No backups are written. This is a source tree under version control, and a
    tool that scatters ``.bak`` files beside the originals is a worse neighbour
    than one that trusts git.

    A write that fails is collected rather than raised. Files are written one at
    a time, so raising on the second of five left the tree half-modified and the
    caller holding a traceback instead of the list of what had already changed --
    from a tool whose entire job is editing source files. The scanner already
    treats an unreadable file as something to report and carry on from; the write
    path now matches it.
    """
    written: list[Path] = []
    failed: list[tuple[Path, str]] = []
    for patch in patches:
        if not patch.changed:
            continue
        try:
            # newline="" writes the string's own separators verbatim instead of
            # translating "\n" to os.linesep, which would corrupt a CRLF file on
            # Windows and an LF file nowhere.
            with patch.path.open("w", encoding="utf-8", newline="") as handle:
                handle.write(patch.patched)
        except OSError as exc:
            failed.append((patch.path, str(exc)))
            continue
        written.append(patch.path)
    return ApplyResult(written=written, failed=failed)
