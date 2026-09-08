"""Static analysis for the July 2026 alphanumeric CNPJ transition."""

from .fixer import ApplyResult, FilePatch, apply_patches, build_patches, unified_diff
from .rules import RULES, Rule, language_of, rules_for_language
from .scanner import Finding, ScanResult, scan_path, scan_text

__all__ = [
    "RULES",
    "ApplyResult",
    "FilePatch",
    "Finding",
    "Rule",
    "ScanResult",
    "apply_patches",
    "build_patches",
    "language_of",
    "rules_for_language",
    "scan_path",
    "scan_text",
    "unified_diff",
]
