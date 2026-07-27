class ServiceError(Exception):
    """Base exception for service-layer errors."""


class ValidationError(ServiceError):
    """Raised when service input is incomplete or invalid."""


class NotFoundError(ServiceError):
    """Raised when a requested user-owned entity does not exist."""
