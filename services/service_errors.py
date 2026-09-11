"""HTTP-independent errors raised by reusable service operations."""

from __future__ import annotations


class ServiceError(Exception):
    """A service failure carrying the status and detail for the API boundary."""

    def __init__(self, detail: str, *, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code

