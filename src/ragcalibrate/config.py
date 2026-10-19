"""Process configuration: the only module that reads the environment.

Experiment parameters are not environment: they live in versioned YAML whose hash
identifies the run. Never log a Settings object; keep secrets as SecretStr anyway.
"""

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": the shared .env also holds the variables the Postgres container reads.
    model_config = SettingsConfigDict(env_prefix="RAGCALIBRATE_", env_file=".env", extra="ignore")

    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def _must_be_postgres(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("postgresql://", "postgres://")):
            raise ValueError("must be a postgresql:// URL")
        return value


def load_settings() -> Settings:
    """Build Settings from the environment (and .env); raises ValidationError at startup."""
    # Pyright reads the fields as required constructor arguments, but pydantic-settings fills
    # them from the environment. Only this function constructs Settings, so the ignore is here.
    return Settings()  # pyright: ignore[reportCallIssue]
