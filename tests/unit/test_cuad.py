import json
import zipfile
from pathlib import Path

import pytest

from ragcalibrate.corpora import evalsets
from ragcalibrate.corpora.cuad import CuadData, load_cuad

TEXT_A = "SERVICE AGREEMENT between Acme and Bob. Governing law: Delaware. Term: 5 years."
TEXT_B = "LICENSE of Zed. No termination clause here."


def _qa(title: str, category: str, answers: list[tuple[str, int]]) -> dict[str, object]:
    return {
        "id": f"{title}__{category}",
        "question": f"Highlight {category}",
        "is_impossible": not answers,
        "answers": [{"text": t, "answer_start": s} for t, s in answers],
    }


def _contract(title: str, text: str, qas: list[dict[str, object]]) -> dict[str, object]:
    return {"title": title, "paragraphs": [{"context": text, "qas": qas}]}


def make_zip(path: Path, a_answers: list[tuple[str, int]] | None = None) -> Path:
    a_answers = a_answers if a_answers is not None else [("Delaware", TEXT_A.index("Delaware"))]
    contract_a = _contract(
        "A",
        TEXT_A,
        [
            _qa("A", "Governing Law", a_answers),
            _qa("A", "Term", [("5 years", TEXT_A.index("5 years"))]),
        ],
    )
    contract_b = _contract("B", TEXT_B, [_qa("B", "Governing Law", [])])
    full = {"version": "x", "data": [contract_b, contract_a]}  # deliberately unsorted
    test = {"version": "x", "data": [contract_b]}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("CUADv1.json", json.dumps(full))
        z.writestr("test.json", json.dumps(test))
    return path


@pytest.fixture
def data(tmp_path: Path) -> CuadData:
    return load_cuad(make_zip(tmp_path / "data.zip"))


def test_spans_slice_back_to_their_label_text(data: CuadData) -> None:
    texts = {d.id: d.text for d in data.documents}
    for g in data.gold:
        for s in g.spans:
            assert texts[g.document_id][s.start : s.end] == s.text


def test_unanswerable_pair_is_kept(data: CuadData) -> None:
    by_id = {g.query_id: g for g in data.gold}
    assert by_id["B__Governing Law"].spans == ()
    assert not by_id["B__Governing Law"].answerable
    assert by_id["A__Term"].answerable
    assert by_id["A__Term"].category == "Term"


def test_split_follows_test_json_and_never_splits_a_document(data: CuadData) -> None:
    assert data.split_of == {"A": "dev", "B": "test"}
    dev_q, dev_g = data.split("dev")
    test_q, _ = data.split("test")
    assert {q.document_id for q in dev_q}.isdisjoint({q.document_id for q in test_q})
    assert [q.id for q in dev_q] == ["A__Governing Law", "A__Term"]  # sorted
    assert len(dev_g) == len(dev_q)


def test_label_that_does_not_match_the_text_is_rejected(tmp_path: Path) -> None:
    bad = make_zip(tmp_path / "bad.zip", a_answers=[("Delaware", 3)])
    with pytest.raises(ValueError, match="does not match"):
        load_cuad(bad)


def test_query_records_carry_no_label_fields(data: CuadData) -> None:
    fields = set(type(data.queries[0]).model_fields)
    assert fields == {"id", "document_id", "text"}


def test_evalset_bytes_are_deterministic_and_change_with_a_label(tmp_path: Path) -> None:
    first = load_cuad(make_zip(tmp_path / "1.zip"))
    again = load_cuad(make_zip(tmp_path / "2.zip"))
    _, m1 = evalsets.build(first, "src")
    _, m2 = evalsets.build(again, "src")
    assert m1.evalset_hash == m2.evalset_hash
    moved = load_cuad(
        make_zip(tmp_path / "3.zip", a_answers=[("Delaware", TEXT_A.index("Delaware"))])
    )
    assert evalsets.build(moved, "src")[1].evalset_hash == m1.evalset_hash
    different = load_cuad(make_zip(tmp_path / "4.zip", a_answers=[]))
    assert evalsets.build(different, "src")[1].evalset_hash != m1.evalset_hash


def test_write_read_roundtrip_and_tamper_detection(data: CuadData, tmp_path: Path) -> None:
    files, manifest = evalsets.build(data, "src")
    evalsets.write(tmp_path, files, manifest)
    assert evalsets.verify(tmp_path) == manifest
    assert evalsets.read_queries(tmp_path, "dev") == list(data.split("dev")[0])
    assert evalsets.read_gold(tmp_path, "test") == list(data.split("test")[1])
    assert manifest.counts["dev.answerable"] == 2
    (tmp_path / "cuad-dev.gold.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="does not match"):
        evalsets.verify(tmp_path)


def test_service_package_does_not_reference_eval_sets() -> None:
    service = Path(__file__).parents[2] / "src" / "ragcalibrate" / "service"
    for path in service.rglob("*.py"):
        source = path.read_text("utf-8")
        for forbidden in ("evalsets", "ragcalibrate.harness", "corpora.schema import Gold"):
            assert forbidden not in source, f"{path.name} mentions {forbidden}"
