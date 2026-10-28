"""Write and read the hashed eval-set files (harness side only; the service never imports this).

Per split two files: `cuad-<split>.queries.jsonl` (what the system under test may be asked) and
`cuad-<split>.gold.jsonl` (labels), kept apart so the gold file can never be loaded by accident.
The bytes are deterministic (sorted records, sorted keys, UTF-8, LF), so the sha256 in
`cuad.manifest.json` identifies the eval set: change a query, a span or a split assignment and
the hash changes.
"""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

from ragcalibrate.corpora.cuad import CuadData
from ragcalibrate.corpora.schema import Gold, Query, Split

SPLITS: tuple[Split, ...] = ("dev", "test")
MANIFEST = "cuad.manifest.json"


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
