"""The harness's only way to reach the system under test: HTTP, through the contract models.

Any service that implements the contract in `ragcalibrate.contract` can be measured with no
change here; nothing in this package imports the service (import-linter enforces it).
"""

import httpx
from pydantic import ValidationError

from ragcalibrate.contract import Problem, RetrieveRequest, RetrieveResponse

# Local retrieval answers in milliseconds; this bounds a hung service, not a slow one.
TIMEOUT = httpx.Timeout(30.0)


class SutError(Exception):
    """The system under test answered with an error. `code` is its stable problem code."""

    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(f"{status} {code}: {detail}")
        self.status = status
        self.code = code


class HttpSut:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        response = await self._client.post("/retrieve", json=request.model_dump(mode="json"))
        if response.is_success:
            # Parsed strictly: a response that breaks the contract fails here, not in a metric.
            return RetrieveResponse.model_validate_json(response.content)
        raise _error(response)


def _error(response: httpx.Response) -> SutError:
    try:
        problem = Problem.model_validate_json(response.content)
    except ValidationError:
        # Not a problem body (a proxy, or a service that ignores the contract): keep the status.
        return SutError(response.status_code, "unknown", response.text[:200])
    return SutError(problem.status, problem.code, problem.detail)
