"""Write and read the hashed eval-set files (harness side only; the service never imports this).

Per split two files: `cuad-<split>.queries.jsonl` (what the system under test may be asked) and
`cuad-<split>.gold.jsonl` (labels), kept apart so the gold file can never be loaded by accident.
The bytes are deterministic (sorted records, sorted keys, UTF-8, LF), so the sha256 in
`cuad.manifest.json` identifies the eval set: change a query, a span or a split assignment and
the hash changes.

The CI subset (`cuad-dev-ci.json`, plan step 4.5) is a fixed sample of dev documents for PR
gating. It has its own hash and stays out of `evalset_hash`, so writing or resizing it leaves
the eval set's identity, and every stored run, as they were.
"""

import hashlib
import json
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from ragcalibrate.corpora.cuad import CuadData
from ragcalibrate.corpora.schema import Gold, Query, Split

SPLITS: tuple[Split, ...] = ("dev", "test")
MANIFEST = "cuad.manifest.json"
CI_SUBSET = "cuad-dev-ci.json"
STRATA = 3  # terciles of document length in characters (docs/eval-spec.md section 7)


class Manifest(BaseModel):
    source_sha256: str
    files: dict[str, str]  # file name -> sha256 of its bytes
    counts: dict[str, int]  # "<split>.<what>" -> count
    evalset_hash: str


def _jsonl(records: list[BaseModel]) -> bytes:
    lines = [
        json.dumps(r.model_dump(mode="json"), sort_keys=True, ensure_ascii=False) for r in records
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(data: CuadData, source_sha256: str) -> tuple[dict[str, bytes], Manifest]:
    """The eval-set files as bytes, plus the manifest that hashes them."""
    files: dict[str, bytes] = {}
    counts: dict[str, int] = {}
    for split in SPLITS:
        queries, gold = data.split(split)
        files[f"cuad-{split}.queries.jsonl"] = _jsonl(list(queries))
        files[f"cuad-{split}.gold.jsonl"] = _jsonl(list(gold))
        counts[f"{split}.documents"] = len({q.document_id for q in queries})
        counts[f"{split}.queries"] = len(queries)
        counts[f"{split}.answerable"] = sum(g.answerable for g in gold)
    hashes = {name: _sha256(content) for name, content in sorted(files.items())}
    evalset_hash = _sha256("".join(f"{n}:{h}\n" for n, h in hashes.items()).encode())
    return files, Manifest(
        source_sha256=source_sha256, files=hashes, counts=counts, evalset_hash=evalset_hash
    )


def write(directory: Path, files: dict[str, bytes], manifest: Manifest) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (directory / name).write_bytes(content)
    (directory / MANIFEST).write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")


def read_manifest(directory: Path) -> Manifest:
    return Manifest.model_validate_json((directory / MANIFEST).read_text(encoding="utf-8"))


def verify(directory: Path) -> Manifest:
    """Re-hash the files on disk against the manifest; raise if any differ or are missing."""
    manifest = read_manifest(directory)
    for name, expected in manifest.files.items():
        path = directory / name
        if not path.exists() or _sha256(path.read_bytes()) != expected:
            raise ValueError(f"{name} does not match {MANIFEST}: regenerate with `make evalsets`")
    return manifest


def read_queries(directory: Path, split: Split) -> list[Query]:
    path = directory / f"cuad-{split}.queries.jsonl"
    return [Query.model_validate_json(line) for line in path.read_text("utf-8").splitlines()]


def read_gold(directory: Path, split: Split) -> list[Gold]:
    path = directory / f"cuad-{split}.gold.jsonl"
    return [Gold.model_validate_json(line) for line in path.read_text("utf-8").splitlines()]


def _subset_hash(documents: tuple[str, ...]) -> str:
    # The sorted ids, one per line: `shasum -a 256` over that list gives the same value.
    return _sha256("".join(f"{d}\n" for d in documents).encode())


class CiSubset(BaseModel):
    """The CI subset: which dev documents, how they were drawn, and a hash of the list.

    `evalset_hash` names the eval set it was drawn from; `subset_hash` is its identity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    seed: int
    size: int
    evalset_hash: str
    documents: tuple[str, ...]  # sorted, distinct
    subset_hash: str

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if list(self.documents) != sorted(set(self.documents)):
            raise ValueError("documents must be sorted and distinct")
        if len(self.documents) != self.size:
            raise ValueError(f"size is {self.size} but {len(self.documents)} documents are listed")
        if self.subset_hash != _subset_hash(self.documents):
            raise ValueError("subset_hash does not match the documents: regenerate the subset")
        return self


def ci_subset(data: CuadData, *, evalset_hash: str, size: int, seed: int) -> CiSubset:
    """`size` dev documents, stratified by length (docs/eval-spec.md section 7).

    The dev documents, sorted by (length in characters, id), are cut into three strata of
    near-equal count, and the size is cut the same way: stratum i holds documents
    [i*n//3, (i+1)*n//3) and gets (i+1)*size//3 - i*size//3 of them. Within a stratum the
    documents with the smallest sha256(f"{seed}:{id}") are drawn. A hash rather than numpy's
    generator, whose streams may change between versions, so a seed draws the same documents on
    any machine; and a larger size only adds documents to a smaller one's draw.
    """
    dev = sorted((len(d.text), d.id) for d in data.documents if data.split_of[d.id] == "dev")
    n = len(dev)
    if not STRATA <= size <= n:
        raise ValueError(f"size must be from {STRATA} to {n} (the dev documents), got {size}")
    chosen: list[str] = []
    for i in range(STRATA):
        stratum = [doc_id for _, doc_id in dev[i * n // STRATA : (i + 1) * n // STRATA]]
        quota = (i + 1) * size // STRATA - i * size // STRATA
        chosen += sorted(stratum, key=lambda d: _sha256(f"{seed}:{d}".encode()))[:quota]
    documents = tuple(sorted(chosen))
    return CiSubset(
        seed=seed,
        size=size,
        evalset_hash=evalset_hash,
        documents=documents,
        subset_hash=_subset_hash(documents),
    )


def write_ci_subset(directory: Path, subset: CiSubset) -> None:
    path = directory / CI_SUBSET
    path.write_text(subset.model_dump_json(indent=2) + "\n", encoding="utf-8")


def read_ci_subset(directory: Path) -> CiSubset:
    """Read the subset, checking that its list matches its size and its hash."""
    return CiSubset.model_validate_json((directory / CI_SUBSET).read_text(encoding="utf-8"))
