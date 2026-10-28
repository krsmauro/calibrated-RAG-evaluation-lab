"""The HTTP contract: what the harness may send, and what the service documents (plan step 2.7)."""

from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import ValidationError

from ragcalibrate.contract import Problem, RetrieveRequest
from ragcalibrate.service.app import create_app
from ragcalibrate.service.routes import SCHEMA_REVISION

ROOT = Path(__file__).parents[2]
VALID: dict[str, Any] = {
    "query": "Which law governs?",
    "corpus": "cuad",
    "doc_id": "some contract",
    "strategy": "dense",
    "chunker_id": "c1",
    "k": 5,
}


def test_a_request_has_no_field_that_could_carry_a_label() -> None:
    labels = {"gold", "spans", "answerable", "expected", "category", "answer"}
    assert not labels & set(RetrieveRequest.model_fields)


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"gold": [[0, 10]]}, "Extra inputs are not permitted"),
        ({"k": "5"}, "Input should be a valid integer"),
        ({"k": 0}, "greater than or equal to 1"),
        ({"strategy": "bm25"}, "Input should be 'fts' or 'dense'"),
        ({"strategy": "fts", "embedder_id": "some-model"}, "fts uses no embedding model"),
    ],
)
def test_bad_requests_are_rejected_not_coerced(change: dict[str, Any], error: str) -> None:
    with pytest.raises(ValidationError, match=error):
        RetrieveRequest.model_validate(VALID | change)


def test_openapi_documents_the_contract_models_and_problem_errors() -> None:
    spec = create_app().openapi()
    post = spec["paths"]["/retrieve"]["post"]
    ref = "#/components/schemas/"
    assert post["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": ref + "RetrieveRequest"
    }
    responses = post["responses"]
    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": ref + "RetrieveResponse"
    }
    problem = {
        "application/problem+json": {"schema": Problem.model_json_schema(mode="serialization")}
    }
    for status in ("404", "422", "500"):
        assert responses[status]["content"] == problem
    assert spec["paths"]["/readyz"]["get"]["responses"]["503"]["content"] == problem
    # FastAPI's default 422 body is never sent (errors.py answers with problem details).
    assert "HTTPValidationError" not in spec["components"]["schemas"]
    assert set(spec["paths"]) == {"/healthz", "/readyz", "/retrieve"}


def test_readiness_expects_the_latest_migration() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    assert ScriptDirectory.from_config(config).get_current_head() == SCHEMA_REVISION
