"""Client for the external supplier directory.

Everything about the upstream API - auth, retries, its response shape - stops
here. The services above only ever see a dict or a domain error.
"""

import asyncio
import logging
from typing import Any, Protocol

import httpx

from app.errors import UpstreamNotFound, UpstreamUnavailable

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class SupplierSource(Protocol):
    """What the ingestion service needs from an upstream directory."""

    async def fetch(self, external_id: str) -> dict[str, Any]: ...


class SupplierDirectoryClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
    ) -> None:
        self._client = client
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds

    async def fetch(self, external_id: str) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.get(f"/suppliers/{external_id}")
            except httpx.HTTPError as exc:  # timeout, DNS, connection reset
                last_error = exc
            else:
                if response.status_code == 404:
                    raise UpstreamNotFound(
                        f"Supplier {external_id!r} is not in the directory"
                    )
                if response.status_code not in RETRYABLE_STATUS:
                    response.raise_for_status()
                    return response.json()
                last_error = httpx.HTTPStatusError(
                    f"upstream returned {response.status_code}",
                    request=response.request,
                    response=response,
                )

            if attempt < self._max_attempts:
                delay = self._backoff_seconds * 2 ** (attempt - 1)
                logger.warning(
                    "supplier directory attempt %s/%s failed (%s), retrying in %.1fs",
                    attempt,
                    self._max_attempts,
                    last_error,
                    delay,
                )
                await asyncio.sleep(delay)

        raise UpstreamUnavailable(
            f"Supplier directory unavailable after {self._max_attempts} attempts"
        ) from last_error
