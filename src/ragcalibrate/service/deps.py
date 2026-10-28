"""What the routes need, created once in the app's lifespan and handed out by a dependency."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from fastapi import Request
from psycopg_pool import AsyncConnectionPool

from ragcalibrate.ingest.embedding import Vectors

Embed = Callable[[Sequence[str]], Vectors]


@dataclass(frozen=True)
class Resources:
    pool: AsyncConnectionPool
    # embedder id -> its embed function. Synchronous and CPU-bound: call it via asyncio.to_thread.
    embedders: Mapping[str, Embed]
    default_embedder_id: str


def get_resources(request: Request) -> Resources:
    # app.state is untyped; the lifespan in app.py is the only writer of this attribute.
    resources: Resources = request.app.state.resources
    return resources
