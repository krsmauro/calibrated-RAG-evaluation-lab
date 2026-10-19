"""Measure the CUAD facts that docs/eval-spec.md depends on (plan step 1.7).

Reads data/raw/cuad/data.zip in memory (never extracts it). Standard library only.
Usage: python -I scripts/cuad_facts.py
"""

import json
import statistics
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

ZIP = Path("data/raw/cuad/data.zip")


def load(archive: zipfile.ZipFile, name: str) -> list[dict[str, Any]]:
    return json.loads(archive.read(name))["data"]


def quantiles(values: list[int]) -> dict[str, float]:
    qs = statistics.quantiles(values, n=100)
    return {
        "min": min(values),
        "p25": qs[24],
        "median": statistics.median(values),
        "p75": qs[74],
        "p95": qs[94],
        "max": max(values),
        "mean": round(statistics.fmean(values), 1),
    }


def main() -> None:
    archive = zipfile.ZipFile(ZIP)
    full = load(archive, "CUADv1.json")
    test = load(archive, "test.json")
    train_sep = load(archive, "train_separate_questions.json")

    def report(title: str, value: Any) -> None:
        print(f"{title}: {value}")

    # --- shape: one paragraph (the whole contract) per document?
    report("paragraphs per doc (full)", Counter(len(d["paragraphs"]) for d in full))
    docs = {d["title"]: d["paragraphs"][0] for d in full}
    report("contracts (full)", len(docs))

    # --- categories and pairs
    pairs = []  # (title, category, answers)
    for title, para in docs.items():
        for qa in para["qas"]:
            pairs.append((title, qa["id"].rsplit("__", 1)[1], qa["answers"], qa["is_impossible"]))
    categories = sorted({p[1] for p in pairs})
    report("categories", len(categories))
    report("qas per contract", Counter(len(p["qas"]) for p in docs.values()))
    report("pairs (contract x category)", len(pairs))
    report("distinct (title, category)", len({(p[0], p[1]) for p in pairs}))

    # --- unanswerable share and consistency of the is_impossible flag
    empty = sum(1 for p in pairs if not p[2])
    flagged = sum(1 for p in pairs if p[3])
    report("pairs with no gold span", f"{empty} ({empty / len(pairs):.1%})")
    report("is_impossible=True", f"{flagged} ({flagged / len(pairs):.1%})")
    report(
        "flag disagrees with empty answers",
        sum(1 for p in pairs if bool(p[3]) != (not p[2])),
    )
    per_cat: dict[str, list[int]] = {c: [0, 0] for c in categories}
    for _, cat, answers, _ in pairs:
        per_cat[cat][0] += 1
        per_cat[cat][1] += 0 if answers else 1
    ranked = sorted(per_cat.items(), key=lambda kv: kv[1][1] / kv[1][0])
    report("lowest unanswerable share", [(c, f"{v[1] / v[0]:.0%}") for c, v in ranked[:4]])
    report("highest unanswerable share", [(c, f"{v[1] / v[0]:.0%}") for c, v in ranked[-4:]])

    # --- gold spans per answerable pair
    answerable = [p for p in pairs if p[2]]
    report("answerable pairs", len(answerable))
    dist = Counter(len(p[2]) for p in answerable)
    report("gold spans per answerable pair", dict(sorted(dist.items())))
    report("total gold spans", sum(len(p[2]) for p in pairs))
    report("answerable pairs with 2+ spans", f"{sum(v for k, v in dist.items() if k > 1)}")

    # --- offsets: text[start:start+len(answer)] == answer
    bad: list[tuple[str, int, str, str]] = []
    nonint = 0
    spans: list[tuple[str, int, int, str]] = []  # title, start, end, text
    for title, _, answers, _ in pairs:
        context = docs[title]["context"]
        for a in answers:
            if not isinstance(a["answer_start"], int):
                nonint += 1
            start = int(a["answer_start"])
            end = start + len(a["text"])
            spans.append((title, start, end, a["text"]))
            if context[start:end] != a["text"]:
                bad.append((title, start, a["text"][:60], context[start:end][:60]))
    report("answer_start not an int (stored as str)", nonint)
    report("labels whose text != context[start:start+len]", f"{len(bad)} of {len(spans)}")
    for b in bad[:3]:
        report("  example", b)
    report(
        "spans past end of document", sum(1 for t, s, e, _ in spans if e > len(docs[t]["context"]))
    )
    report("empty-text spans", sum(1 for s in spans if s[2] == s[1]))

    # --- span shape (matters for the relevance rule and whitespace overlaps)
    lengths = [e - s for _, s, e, _ in spans]
    report("gold span length (chars)", quantiles(lengths))
    report("spans with leading/trailing whitespace", sum(1 for s in spans if s[3] != s[3].strip()))
    overlapping = 0
    for _title, _, answers, _ in pairs:
        iv = sorted(
            (int(a["answer_start"]), int(a["answer_start"]) + len(a["text"])) for a in answers
        )
        if any(iv[i][1] > iv[i + 1][0] for i in range(len(iv) - 1)):
            overlapping += 1
    report("pairs whose gold spans overlap each other", overlapping)

    # --- contract length
    chars = [len(p["context"]) for p in docs.values()]
    words = [len(p["context"].split()) for p in docs.values()]
    report("contract length (chars)", quantiles(chars))
    report("contract length (whitespace words)", quantiles(words))
    report("contract length (rough tokens, chars/4)", quantiles([c // 4 for c in chars]))

    # --- the official splits
    test_titles = {d["title"] for d in test}
    train_titles = {d["title"] for d in train_sep}
    report("test contracts", len(test_titles))
    report("test rows (qas)", sum(len(d["paragraphs"][0]["qas"]) for d in test))
    report("train contracts (train_separate_questions.json)", len(train_titles))
    report(
        "train rows (qas, one per answer span)",
        sum(len(d["paragraphs"][0]["qas"]) for d in train_sep),
    )
    report("train/test title overlap", len(train_titles & test_titles))
    report("train + test == full set of titles", (train_titles | test_titles) == set(docs))
    same_text = all(
        d["paragraphs"][0]["context"] == docs[d["title"]]["context"] for d in test + train_sep
    )
    report("contexts identical to the full file", same_text)

    # Compare labels as sets: test.json lists some questions' answers in a different order.
    def labels(doc_pairs: list[tuple[str, str, list[dict[str, Any]], bool]]) -> set[Any]:
        return {
            (t, c, frozenset((a["text"], int(a["answer_start"])) for a in ans))
            for t, c, ans, _ in doc_pairs
        }

    test_pairs_in_test_json = [
        (d["title"], qa["id"].rsplit("__", 1)[1], qa["answers"], qa["is_impossible"])
        for d in test
        for qa in d["paragraphs"][0]["qas"]
    ]
    full_answers = labels([p for p in pairs if p[0] in test_titles])
    test_answers = labels(test_pairs_in_test_json)
    report("test.json labels identical to the full file (as sets)", full_answers == test_answers)
    test_pairs = [p for p in pairs if p[0] in test_titles]
    dev_pairs = [p for p in pairs if p[0] not in test_titles]
    report("test pairs / unanswerable", (len(test_pairs), sum(1 for p in test_pairs if not p[2])))
    report("dev pairs / unanswerable", (len(dev_pairs), sum(1 for p in dev_pairs if not p[2])))
    report("dev contracts", len({p[0] for p in dev_pairs}))


if __name__ == "__main__":
    main()
