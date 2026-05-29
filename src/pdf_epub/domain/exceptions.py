class DomainError(Exception):
    """Base for all domain-level errors."""


class ExtractionError(DomainError):
    """Raised when PDF content extraction fails."""


class ScannedPdfError(DomainError):
    """Raised when OCR processing of a scanned PDF fails."""


class BuildError(DomainError):
    """Raised when EPUB assembly fails."""


class InvalidJobStateError(DomainError):
    """Raised when a job transition is not allowed for its current status."""
