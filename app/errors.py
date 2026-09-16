"""Domain errors.

Services raise these; the API layer is the only place that knows about HTTP.
"""


class DomainError(Exception):
    """Base class for errors the service raises on purpose."""


class SupplierAlreadyExists(DomainError):
    def __init__(self, external_id: str) -> None:
        super().__init__(f"Supplier with external_id {external_id!r} already exists")
        self.external_id = external_id


class SupplierNotFound(DomainError):
    def __init__(self, supplier_id: int | str) -> None:
        super().__init__(f"Supplier {supplier_id!r} not found")
        self.supplier_id = supplier_id


class UpstreamNotFound(DomainError):
    """The external directory does not know this supplier."""


class UpstreamUnavailable(DomainError):
    """The external directory failed or timed out after every retry."""


class EnrichmentFailed(DomainError):
    """The model call failed or returned something unusable.

    `retryable` tells the worker whether another attempt could succeed: a rate
    limit or a dropped connection is worth retrying, a refusal is not.
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable
