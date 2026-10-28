"""Shapes shared by the corpus adapters and the eval-set files.

Offsets are half-open character offsets [start, end) into the raw, un-normalized document text
exactly as the dataset shipped it. Queries and gold labels are deliberately separate types: the
service may see a Query (never the gold), the harness reads both (ADR 0005).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

Split = Literal["dev", "test"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Document(_Frozen):
    id: str
    text: str


class Query(_Frozen):
    """What the harness may send to the system under test: an id, a document and the question."""

    id: str
    document_id: str
    text: str


class GoldSpan(_Frozen):
    start: int
    end: int
    text: str

    @model_validator(mode="after")
    def _non_empty(self) -> "GoldSpan":
        if not 0 <= self.start < self.end:
            raise ValueError(f"bad span offsets [{self.start}, {self.end})")
        return self


class Gold(_Frozen):
    """Everything the harness knows about a query that the service must never see.

    Spans are kept exactly as labeled (they may overlap each other); metrics merge them.
    `answerable` is derived from the spans, so the two cannot disagree.
    """

    query_id: str
    document_id: str
    category: str
    spans: tuple[GoldSpan, ...]

    @property
    def answerable(self) -> bool:
        return bool(self.spans)
