"""The HTTP contract between the harness and the system under test: one definition per shape.

The service and the harness's HTTP adapter both import these models and neither redeclares
them (skill XC-CRITICAL-3), so the two sides cannot drift apart. This module is the only thing
they share. A request carries what a real user of the service would send and nothing more: no
gold span, category or answerability (ADR 0005, skill EVAL-CRITICAL-1).

Models are strict: "5" is not accepted for 5, and an unknown field is an error, not ignored.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_K = 100
MAX_QUERY_CHARS = 2_000

# S2 (Design §7). S1, S3 and S4 are added in plan phase 3.
Strategy = Literal["dense"]


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RetrieveRequest(_Wire):
    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    corpus: str = Field(min_length=1, examples=["cuad"])
    doc_id: str = Field(min_length=1, description="The document's id in its source dataset.")
    strategy: Strategy
    chunker_id: str = Field(min_length=1)
    embedder_id: str | None = Field(
        default=None,
        description="Embedding model for dense strategies. Default: the service's local model.",
    )
    k: int = Field(ge=1, le=MAX_K)


class RetrievedChunk(_Wire):
    chunk_id: int
    start_char: int = Field(ge=0, description="Half-open character offsets into the raw text.")
    end_char: int
    text: str
    score: float = Field(description="Higher is better. Dense: cosine similarity.")

    @model_validator(mode="after")
    def _ordered(self) -> "RetrievedChunk":
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")
        return self


class RetrieveResponse(_Wire):
    strategy: Strategy
    chunker_id: str
    embedder_id: str | None = Field(description="The model actually used; null for lexical.")
    chunks: list[RetrievedChunk] = Field(
        description="Best first; fewer than k when the document has fewer chunks."
    )


class Problem(_Wire):
    """Every error response body: RFC 9457 problem details plus a stable machine-readable code."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: str
