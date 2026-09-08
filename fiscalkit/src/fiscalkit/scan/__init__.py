"""Static analysis for the July 2026 alphanumeric CNPJ transition."""

from .rules import RULES, Rule, language_of, rules_for_language
from .scanner import Finding, ScanResult, scan_path, scan_text

__all__ = [
    "RULES",
    "Finding",
    "Rule",
    "ScanResult",
    "language_of",
    "rules_for_language",
    "scan_path",
    "scan_text",
]
