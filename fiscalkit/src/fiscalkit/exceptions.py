"""Exception hierarchy for fiscalkit.

Every error raised by the library derives from :class:`FiscalKitError`, so callers
can catch the whole surface with a single ``except`` when they do not care which
specific rule was violated.
"""

from __future__ import annotations


class FiscalKitError(Exception):
    """Base class for every error raised by fiscalkit."""


class ValidationError(FiscalKitError):
    """A document or code failed a structural or check-digit rule.

    Attributes:
        value: The offending input, normalized when normalization succeeded.
        reason: Machine-readable reason code, useful for i18n on the caller side.
    """

    def __init__(
        self, message: str, *, value: str | None = None, reason: str | None = None
    ) -> None:
        super().__init__(message)
        self.value = value
        self.reason = reason


class ParseError(FiscalKitError):
    """A document could not be parsed into the expected structure."""


class UnsupportedDocumentError(ParseError):
    """The XML parsed cleanly but is not a document type this library handles."""
