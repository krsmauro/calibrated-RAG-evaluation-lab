"""The system under test: a FastAPI app built by `create_app` (`make serve` runs it).

The lifespan opens the Postgres pool and loads the embedding model once; routes receive them
through `deps.get_resources`. Importing this module does no work.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from ragcalibrate.config import load_settings
from ragcalibrate.ingest.embedding import DEFAULT_MODEL_DIR, EMBEDDER_ID, Embedder
from ragcalibrate.logs import configure_logging
from ragcalibrate.service import errors, routes
from ragcalibrate.service.deps import Resources

POOL_SIZE = 10
# Every database call is bounded: waiting for a connection, and each statement.
POOL_TIMEOUT_S = 5.0
STATEMENT_TIMEOUT_MS = 5_000


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        url = load_settings().database_url.get_secret_value()
        embedder = Embedder(DEFAULT_MODEL_DIR)
        async with AsyncConnectionPool(
            url,
            connection_class=AsyncConnection,
            min_size=1,
            max_size=POOL_SIZE,
            timeout=POOL_TIMEOUT_S,
            kwargs={"options": f"-c statement_timeout={STATEMENT_TIMEOUT_MS}"},
            open=False,
        ) as pool:
            # Fail at startup, with a readable error, if the database cannot be reached at all.
            await pool.wait(timeout=POOL_TIMEOUT_S)
            app.state.resources = Resources(
                pool=pool, embedders={EMBEDDER_ID: embedder.embed}, default_embedder_id=EMBEDDER_ID
            )
            yield

    configure_logging()
    app = FastAPI(title="ragcalibrate RAG service", lifespan=lifespan)
    errors.register(app)
    app.include_router(routes.router)
    return app
