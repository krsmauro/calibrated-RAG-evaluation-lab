"""The CI subset (plan step 4.5): stratified by length, reproducible from a seed, dev only."""

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ragcalibrate.corpora import evalsets
from ragcalibrate.corpora.cuad import CuadData, load_cuad
from ragcalibrate.corpora.schema import Document, Split

ROOT = Path(__file__).parents[2]
ZIP = ROOT / "data" / "raw" / "cuad" / "data.zip"
HASH = "e" * 64


def _data(dev_lengths: list[int], test_lengths: tuple[int, ...] = ()) -> CuadData:
    docs = [Document(id=f"d{i:02}", text="x" * n) for i, n in enumerate(dev_lengths)]
    docs += [Document(id=f"t{i:02}", text="x" * n) for i, n in enumerate(test_lengths)]
    split_of: dict[str, Split] = {d.id: "dev" if d.id[0] == "d" else "test" for d in docs}
    return CuadData(tuple(docs), (), (), split_of)


# Nine dev documents whose ids do not follow their lengths, and test documents of lengths that
# fall inside every tercile, so a draw that sorted by id or kept test documents would show.
LENGTHS = [50, 90, 10, 70, 30, 60, 20, 80, 40]
TERCILE = {f"d{i:02}": (n - 1) // 30 for i, n in enumerate(LENGTHS)}  # 10-30, 40-60, 70-90
DATA = _data(LENGTHS, test_lengths=(15, 55, 85))


def _per_tercile(subset: evalsets.CiSubset) -> list[int]:
    counts = Counter(TERCILE[d] for d in subset.documents)
    return [counts[t] for t in range(3)]


@pytest.mark.parametrize("seed", range(20))
def test_size_three_draws_one_document_per_tercile(seed: int) -> None:
    subset = evalsets.ci_subset(DATA, evalset_hash=HASH, size=3, seed=seed)
    assert _per_tercile(subset) == [1, 1, 1]


@pytest.mark.parametrize(
    ("size", "expected"),
    [(4, [1, 1, 2]), (5, [1, 2, 2]), (6, [2, 2, 2]), (7, [2, 2, 3]), (9, [3, 3, 3])],
)
def test_size_is_split_like_the_strata(size: int, expected: list[int]) -> None:
    # Stratum i gets (i+1)*size//3 - i*size//3: for 4, 1 - 0, 2 - 1 and 4 - 2.
    assert _per_tercile(evalsets.ci_subset(DATA, evalset_hash=HASH, size=size, seed=1)) == expected


def test_within_a_stratum_the_smallest_seeded_hashes_are_drawn() -> None:
    def rank(doc_id: str) -> str:
        return hashlib.sha256(f"7:{doc_id}".encode()).hexdigest()

    subset = evalsets.ci_subset(DATA, evalset_hash=HASH, size=3, seed=7)
    for tercile in range(3):
        members = [d for d, t in TERCILE.items() if t == tercile]
        drawn = [d for d in subset.documents if TERCILE[d] == tercile]
        assert drawn == [min(members, key=rank)]


def test_never_draws_a_test_document() -> None:
    subset = evalsets.ci_subset(DATA, evalset_hash=HASH, size=9, seed=1)
    assert subset.documents == tuple(sorted(TERCILE))


def test_the_same_seed_draws_the_same_documents_and_another_seed_others() -> None:
    data = _data(list(range(100, 3100, 100)))  # 30 dev documents, 10 per stratum
    first = evalsets.ci_subset(data, evalset_hash=HASH, size=6, seed=1)
    assert evalsets.ci_subset(data, evalset_hash=HASH, size=6, seed=1) == first
    assert evalsets.ci_subset(data, evalset_hash=HASH, size=6, seed=2) != first


def test_a_larger_size_only_adds_documents() -> None:
    data = _data([(i * 37) % 101 + 1 for i in range(30)])
    draws = [
        set(evalsets.ci_subset(data, evalset_hash=HASH, size=s, seed=3).documents)
        for s in range(3, 31)
    ]
    for smaller, larger in pairwise(draws):
        assert smaller < larger


@pytest.mark.parametrize("size", [2, 10])
def test_a_size_outside_three_to_the_dev_count_raises(size: int) -> None:
    with pytest.raises(ValueError, match="size must be from 3 to 9"):
        evalsets.ci_subset(DATA, evalset_hash=HASH, size=size, seed=1)


def test_subset_hash_is_the_sha256_of_the_ids_one_per_line() -> None:
    subset = evalsets.ci_subset(DATA, evalset_hash=HASH, size=4, seed=1)
    listed = "".join(f"{d}\n" for d in subset.documents).encode()
    assert subset.subset_hash == hashlib.sha256(listed).hexdigest()


def test_round_trip(tmp_path: Path) -> None:
    subset = evalsets.ci_subset(DATA, evalset_hash=HASH, size=4, seed=1)
    evalsets.write_ci_subset(tmp_path, subset)
    assert evalsets.read_ci_subset(tmp_path) == subset


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda r: r["documents"].__setitem__(-1, "d99"), "subset_hash does not match"),
        (lambda r: r["documents"].reverse(), "sorted and distinct"),
        (lambda r: r["documents"].pop(), "size is 4 but 3"),
        (lambda r: r.__setitem__("extra", 1), "Extra inputs"),
    ],
)
def test_reading_rejects_an_edited_file(
    tmp_path: Path, edit: Callable[[dict[str, Any]], object], message: str
) -> None:
    evalsets.write_ci_subset(tmp_path, evalsets.ci_subset(DATA, evalset_hash=HASH, size=4, seed=1))
    path = tmp_path / evalsets.CI_SUBSET
    record = json.loads(path.read_text())
    edit(record)
    path.write_text(json.dumps(record))
    with pytest.raises(ValidationError, match=message):
        evalsets.read_ci_subset(tmp_path)


@pytest.mark.skipif(not ZIP.exists(), reason="run `make data` first")
def test_the_committed_subset_regenerates_from_its_seed() -> None:
    data = load_cuad(ZIP)
    committed = evalsets.read_ci_subset(ROOT / "evalsets")
    evalset_hash = evalsets.read_manifest(ROOT / "evalsets").evalset_hash
    assert committed.evalset_hash == evalset_hash
    again = evalsets.ci_subset(
        data, evalset_hash=evalset_hash, size=committed.size, seed=committed.seed
    )
    assert again == committed
    assert all(data.split_of[d] == "dev" for d in committed.documents)
