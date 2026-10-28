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

# Design §7: S1 is "fts" (Postgres full-text search, not BM25: ADR 0009), S2 is "dense", S3 is
# "hybrid" (S1 and S2 fused with Reciprocal Rank Fusion), S4 is "rerank" (S3's top
# rerank_depth chunks rescored by a local cross-encoder, ADR 0013).
Strategy = Literal["fts", "dense", "hybrid", "rerank"]


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
        description="Embedding model for dense and hybrid. Default: the service's local model.",
    )
    k: int = Field(ge=1, le=MAX_K)
    # Fusion parameters are experiment parameters, so the harness always sends them and the run
    # records them; the service has no default to drift from.
    rrf_k: int | None = Field(
        default=None,
        ge=0,
        description="Hybrid and rerank only, and required there: the RRF smoothing constant, k"
        " in 1 / (k + rank) (Cormack et al. 2009 use 60). Not the number of results.",
    )
    fusion_depth: int | None = Field(
        default=None,
        ge=1,
        le=MAX_K,
        description="Hybrid and rerank only, and required there: how many chunks fts and dense"
        " each contribute before fusion. At least k, and for rerank at least rerank_depth.",
    )
    rerank_depth: int | None = Field(
        default=None,
        ge=1,
        le=MAX_K,
        description="Rerank only, and required there: how many of the hybrid ranking's best"
        " chunks the cross-encoder rescores. At least k.",
    )

    @model_validator(mode="after")
    def _parameters_match_strategy(self) -> "RetrieveRequest":
        # Rejected, not ignored: a run config that names a parameter its strategy never uses is
        # a mistake, and the run would record a setting that had no effect.
        if self.strategy == "fts" and self.embedder_id is not None:
            raise ValueError("embedder_id applies to dense retrieval; fts uses no embedding model")
        fused = self.strategy in ("hybrid", "rerank")
        if not fused and (self.rrf_k is not None or self.fusion_depth is not None):
            raise ValueError("rrf_k and fusion_depth apply to the hybrid and rerank strategies")
        if fused and (self.rrf_k is None or self.fusion_depth is None):
            raise ValueError(f"{self.strategy} needs rrf_k and fusion_depth")
        if (self.strategy == "rerank") != (self.rerank_depth is not None):
            raise ValueError("rerank_depth is required for the rerank strategy and only there")
        # Each stage hands the next at least as many chunks as that one keeps.
        if self.rerank_depth is not None and self.rerank_depth < self.k:
            raise ValueError("rerank_depth must be at least k")
        if self.fusion_depth is not None and self.fusion_depth < (self.rerank_depth or self.k):
            raise ValueError("fusion_depth must be at least k, or rerank_depth for rerank")
        return self


class RetrievedChunk(_Wire):
    chunk_id: int
    start_char: int = Field(ge=0, description="Half-open character offsets into the raw text.")
    end_char: int
    text: str
    score: float = Field(
        description="Higher is better. Dense: cosine similarity. FTS: Postgres ts_rank. Hybrid:"
        " the RRF score. Rerank: the cross-encoder's raw score (a logit, often negative). FTS"
        " and hybrid scores are comparable only within one response."
    )

    @model_validator(mode="after")
    def _ordered(self) -> "RetrievedChunk":
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")
        return self


class RetrieveResponse(_Wire):
    strategy: Strategy
    chunker_id: str
    embedder_id: str | None = Field(description="The model actually used; null for lexical.")
    reranker_id: str | None = Field(
        description="The cross-encoder actually used; null unless the strategy is rerank."
    )
    chunks: list[RetrievedChunk] = Field(
        description="Best first; fewer than k when the document has fewer chunks. FTS returns only"
        " chunks that share a word with the query, so it can return fewer than k, or none."
        " Hybrid and rerank return k like dense, since the dense side alone supplies at least k."
    )


class Problem(_Wire):
    """Every error response body: RFC 9457 problem details plus a stable machine-readable code."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: str
