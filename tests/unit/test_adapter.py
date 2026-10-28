"""The harness adapter's readiness check, against a fake transport: no service, no network."""

import httpx
import pytest

from ragcalibrate.harness.adapter import HttpSut, SutNotReady

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def sut(handler: httpx.MockTransport) -> HttpSut:
    return HttpSut(httpx.AsyncClient(transport=handler, base_url="http://sut.test"))


async def test_a_service_that_is_not_listening_is_one_readable_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("All connection attempts failed", request=request)

    with pytest.raises(SutNotReady, match=r"cannot reach http://sut\.test.*ConnectError"):
        await sut(httpx.MockTransport(refuse)).check_ready()


async def test_a_service_that_is_up_but_not_ready_says_why() -> None:
    problem = {
        "title": "Service Unavailable",
        "status": 503,
        "detail": "database schema is at '0002', expected '0003'",
        "code": "not_ready",
    }

    def not_ready(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json=problem)

    with pytest.raises(SutNotReady, match="not ready: 503 not_ready: database schema is at '0002'"):
        await sut(httpx.MockTransport(not_ready)).check_ready()


async def test_a_ready_service_passes() -> None:
    def ready(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/readyz"
        return httpx.Response(200, json={"status": "ready"})

    await sut(httpx.MockTransport(ready)).check_ready()
