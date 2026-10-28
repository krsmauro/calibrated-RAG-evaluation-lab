"""CUAD adapter: documents, queries and gold spans, read straight from the pinned data.zip.

The zip is untrusted input (scripts/fetch_cuad.py verifies its checksum); members are parsed in
memory and never extracted. Pydantic validates the file boundary only.

Unit of a query: one (contract, category) pair from CUADv1.json (finding F-008). A pair with no
gold span is kept as an unanswerable query. The split follows docs/eval-spec.md section 7: the
official test contracts (titles listed in test.json) are test, every other contract is dev.
"""

import zipfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ragcalibrate.corpora.schema import Document, Gold, GoldSpan, Query, Split

CATEGORY_SEPARATOR = "__"


class _RawAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    # Stored as an int in CUADv1.json and as a string in train_separate_questions.json.
    answer_start: int


class _RawQA(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    question: str
    answers: list[_RawAnswer]


class _RawParagraph(BaseModel):
    model_config = ConfigDict(extra="ignore")
    context: str
    qas: list[_RawQA]


class _RawContract(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str
    paragraphs: list[_RawParagraph]


class _RawFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    data: list[_RawContract]


@dataclass(frozen=True)
class CuadData:
    documents: tuple[Document, ...]
    queries: tuple[Query, ...]
    gold: tuple[Gold, ...]
    split_of: dict[str, Split]  # document id -> split

    def split(self, split: Split) -> tuple[tuple[Query, ...], tuple[Gold, ...]]:
        """Queries and gold of one split, ordered by (document id, query id)."""
        wanted = {d for d, s in self.split_of.items() if s == split}
        queries = tuple(q for q in self.queries if q.document_id in wanted)
        gold = tuple(g for g in self.gold if g.document_id in wanted)
        return queries, gold


def _read(archive: zipfile.ZipFile, member: str) -> _RawFile:
    return _RawFile.model_validate_json(archive.read(member))


def load_cuad(zip_path: Path) -> CuadData:
    with zipfile.ZipFile(zip_path) as archive:
        full = _read(archive, "CUADv1.json")
        test_titles = {c.title for c in _read(archive, "test.json").data}

    documents: list[Document] = []
    queries: list[Query] = []
    gold: list[Gold] = []
    split_of: dict[str, Split] = {}
    for contract in sorted(full.data, key=lambda c: c.title):
        if len(contract.paragraphs) != 1:
            raise ValueError(
                f"{contract.title}: expected one paragraph, got {len(contract.paragraphs)}"
            )
        paragraph = contract.paragraphs[0]
        if contract.title in split_of:
            raise ValueError(f"duplicate contract title {contract.title!r}")
        documents.append(Document(id=contract.title, text=paragraph.context))
        split_of[contract.title] = "test" if contract.title in test_titles else "dev"
        for qa in sorted(paragraph.qas, key=lambda q: q.id):
            category = qa.id.rsplit(CATEGORY_SEPARATOR, 1)[1]
            spans = tuple(_span(contract.title, qa, a, paragraph.context) for a in qa.answers)
            queries.append(Query(id=qa.id, document_id=contract.title, text=qa.question))
            gold.append(
                Gold(query_id=qa.id, document_id=contract.title, category=category, spans=spans)
            )

    missing = test_titles - set(split_of)
    if missing:
        raise ValueError(
            f"test.json names contracts absent from CUADv1.json: {sorted(missing)[:3]}"
        )
    if len({q.id for q in queries}) != len(queries):
        raise ValueError("duplicate query ids")
    return CuadData(tuple(documents), tuple(queries), tuple(gold), split_of)


def _span(title: str, qa: _RawQA, answer: _RawAnswer, context: str) -> GoldSpan:
    end = answer.answer_start + len(answer.text)
    # Half-open offsets into the raw text; a mismatch means the label cannot be trusted.
    if context[answer.answer_start : end] != answer.text:
        raise ValueError(
            f"{qa.id}: label text does not match document {title!r} at {answer.answer_start}"
        )
    return GoldSpan(start=answer.answer_start, end=end, text=answer.text)
