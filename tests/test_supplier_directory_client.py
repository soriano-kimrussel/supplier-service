import httpx
import pytest

from app.clients import SupplierDirectoryClient
from app.errors import UpstreamNotFound, UpstreamUnavailable


def _client(handler) -> SupplierDirectoryClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://directory")
    return SupplierDirectoryClient(http_client, max_attempts=3, backoff_seconds=0)


async def test_returns_the_upstream_payload():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/suppliers/SUP-1"
        return httpx.Response(200, json={"id": "SUP-1"})

    assert await _client(handler).fetch("SUP-1") == {"id": "SUP-1"}


async def test_retries_a_server_error_and_then_succeeds():
    attempts = []

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"id": "SUP-1"})

    assert await _client(handler).fetch("SUP-1") == {"id": "SUP-1"}
    assert len(attempts) == 3


async def test_gives_up_after_the_last_attempt():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(UpstreamUnavailable):
        await _client(handler).fetch("SUP-1")


async def test_timeouts_are_retried_too():
    attempts = []

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(UpstreamUnavailable):
        await _client(handler).fetch("SUP-1")
    assert len(attempts) == 3


async def test_a_404_is_not_retried():
    attempts = []

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(404)

    with pytest.raises(UpstreamNotFound):
        await _client(handler).fetch("SUP-1")
    assert len(attempts) == 1
