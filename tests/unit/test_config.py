from pathlib import Path

import pytest
from pydantic import ValidationError

from ragcalibrate.config import load_settings


def test_reads_database_url_from_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here, so only the environment is read
    monkeypatch.setenv("RAGCALIBRATE_DATABASE_URL", "postgresql://u:p@localhost:5433/db")
    settings = load_settings()
    assert settings.database_url.get_secret_value() == "postgresql://u:p@localhost:5433/db"


def test_secret_is_masked_in_repr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here, so only the environment is read
    monkeypatch.setenv("RAGCALIBRATE_DATABASE_URL", "postgresql://u:hunter2@localhost/db")
    assert "hunter2" not in repr(load_settings())


def test_missing_url_fails_at_startup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here, so only the environment is read
    monkeypatch.delenv("RAGCALIBRATE_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        load_settings()


def test_rejects_non_postgres_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here, so only the environment is read
    monkeypatch.setenv("RAGCALIBRATE_DATABASE_URL", "sqlite:///x.db")
    with pytest.raises(ValidationError):
        load_settings()
