"""Alembic environment: online migrations only, URL from the one Settings module."""

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from ragcalibrate.config import load_settings

# Migrations are hand-written SQL, so there is no model metadata to autogenerate from.
# SQLAlchemy is used here only because Alembic needs it; the service will use psycopg directly.
_url = make_url(load_settings().database_url.get_secret_value()).set(
    drivername="postgresql+psycopg"
)

engine = create_engine(_url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()
