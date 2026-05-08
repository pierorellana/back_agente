class DomainError(Exception):
    """Base class for domain errors."""


class BusinessRuleError(DomainError):
    """Raised when a business rule is violated."""


class NotFoundError(DomainError):
    """Raised when a resource cannot be found."""


class IntegrationError(DomainError):
    """Raised when an external integration fails."""
