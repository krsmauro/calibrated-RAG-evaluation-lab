"""Real Postgres with pgvector: one throwaway container per test session, migrated to head.

The image comes from docker-compose.yml, so local development, CI and these tests run the same
Postgres and pgvector versions, set in one place. Needs Docker.
"""

import re
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

ROOT = Path(__file__).parents[2]


def _compose_image() -> str:
    found = re.search(r"^\s*image:\s*(\S+)", (ROOT / "docker-compose.yml").read_text(), re.M)
    assert found, "docker-compose.yml has no image: line"
    return found.group(1)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer(
        # Throwaway credentials for a container that lives only as long as the test session.
        _compose_image(),
        username="test",
        password="test",  # noqa: S106
        dbname="test",
        driver=None,
    ) as postgres:
        url = postgres.get_connection_url()
        # migrations/env.py reads the URL from Settings; the environment overrides .env.
        with pytest.MonkeyPatch.context() as env:
            env.setenv("RAGCALIBRATE_DATABASE_URL", url)
            command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        yield url


@pytest.fixture
def conn(database_url: str) -> Iterator[psycopg.Connection]:
    """An autocommit connection (as the ingest requires) to an empty corpus schema."""
    with psycopg.connect(database_url, autocommit=True) as connection:
        yield connection
        connection.execute("TRUNCATE documents, chunks, chunk_embeddings RESTART IDENTITY")
