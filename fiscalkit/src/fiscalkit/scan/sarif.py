"""Render scan results as SARIF 2.1.0.

SARIF is what GitHub code scanning ingests, so emitting it turns ``fiscalkit
scan`` from a command someone runs once into findings that appear inline on a
pull request, annotated on the exact line, in the Security tab.

Only the subset GitHub actually consumes is produced. The full specification is
enormous and most of it is optional; a minimal, correct document beats a large
one with a schema violation, because GitHub rejects the whole upload on error.
"""

from __future__ import annotations

from typing import Any

from .. import __version__
from .rules import RULES
from .scanner import ScanResult

__all__ = ["SARIF_SCHEMA", "SARIF_VERSION", "to_sarif"]

SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
)
SARIF_VERSION = "2.1.0"

INFORMATION_URI = "https://github.com/williamgritti/fiscalkit"

#: fiscalkit severity -> SARIF level. GitHub renders "error" as a blocking
#: annotation, "warning" as advisory, "note" as informational.
_LEVEL = {"breaks": "error", "risky": "warning", "review": "note"}

#: GitHub also reads this for the Security tab's severity column.
_PROBLEM_SEVERITY = {"breaks": "error", "risky": "warning", "review": "recommendation"}


def _rule_descriptor(rule: Any) -> dict[str, Any]:
    """One SARIF reportingDescriptor for a fiscalkit rule."""
    return {
        "id": rule.id,
        "name": rule.title.replace(" ", ""),
        "shortDescription": {"text": rule.title},
        "fullDescription": {"text": rule.explanation},
        "help": {
            "text": f"{rule.explanation}\n\nFix: {rule.fix}",
            "markdown": f"{rule.explanation}\n\n**Fix:** {rule.fix}",
        },
        "helpUri": INFORMATION_URI,
        "defaultConfiguration": {"level": _LEVEL.get(rule.severity, "note")},
        "properties": {
            "problem.severity": _PROBLEM_SEVERITY.get(rule.severity, "recommendation"),
            "tags": ["cnpj", "brazil", "compliance", "in-rfb-2229-2024"],
        },
    }


def to_sarif(result: ScanResult) -> dict[str, Any]:
    """Convert *result* into a SARIF 2.1.0 document.

    Every rule is declared in ``tool.driver.rules``, not only the ones that
    matched, so the Security tab can describe a rule even when a later scan
    reports zero findings for it.
    """
    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "fiscalkit",
                        "version": __version__,
                        "semanticVersion": __version__,
                        "informationUri": INFORMATION_URI,
                        "rules": [_rule_descriptor(rule) for rule in RULES],
                    }
                },
                "results": [
                    {
                        "ruleId": finding.rule_id,
                        "level": _LEVEL.get(finding.severity, "note"),
                        "message": {
                            "text": f"{finding.title}. {finding.explanation} Fix: {finding.fix}"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    # SARIF requires a relative, forward-slashed URI.
                                    "artifactLocation": {
                                        "uri": finding.path.replace("\\", "/"),
                                        "uriBaseId": "%SRCROOT%",
                                    },
                                    "region": {
                                        "startLine": finding.line,
                                        "snippet": {"text": finding.excerpt},
                                    },
                                }
                            }
                        ],
                    }
                    for finding in result.sorted_findings()
                ],
            }
        ],
    }
