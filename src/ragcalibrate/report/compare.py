"""Compare stored runs with a baseline, metric by metric (plan step 4.4; Design §8.5).

Each metric gets the baseline and candidate means over the queries both runs define it for, the
mean paired difference, its 95% interval from the paired, document-clustered bootstrap, and its
n queries and n documents. Only the primary metric gets a gate outcome; the others are shown
and never gate (docs/eval-spec.md §6.1). The report renders as Markdown and as HTML, with the
same content.

Pure: the caller reads the run store and writes the files.
"""

import html
import math
from collections.abc import Mapping, Sequence
from typing import NamedTuple

from ragcalibrate.stats.bootstrap import CONFIDENCE, N_RESAMPLES, Interval, paired_cluster_bootstrap
from ragcalibrate.stats.gate import Outcome, decide

# eval-spec §6.1: the first candidate metric whose best dev mean is below 0.95. recall@5 is,
# for S1 to S4 on C1 (checked in steps 2.10 and 3.9, F-004).
PRIMARY = "recall@5"
DELTA = 0.02  # eval-spec §6.3, provisional: the smallest regression worth blocking
# eval-spec §6.2 and F-003: below about 40 contracts the clustered interval under-covers, so a
# comparison with fewer is Inconclusive and no interval is computed.
MIN_DOCUMENTS = 40
SEED = 20261104  # fixed, so a report regenerates exactly; printed in the report


class NotComparable(Exception):
    """The two runs cannot be paired, or should not be without --force."""


class StoredRun(NamedTuple):
    id: str
    split: str
    strategy: str
    chunker_id: str
    git_sha: str
    dirty: bool
    evalset_hash: str
    config_hash: str
    metrics: Mapping[
        str, Mapping[str, float | None]
    ]  # query id -> metric -> value; None: undefined
    document_of: Mapping[str, str]  # query id -> document id, the bootstrap's cluster


class Row(NamedTuple):
    metric: str
    baseline: float  # mean over the paired queries
    candidate: float
    difference: float  # candidate - baseline
    interval: Interval | None  # None: fewer than MIN_DOCUMENTS documents, not computed
    n_queries: int
    n_documents: int
    outcome: Outcome | None  # the gate's outcome; None for a metric that does not gate
    note: str


class Comparison(NamedTuple):
    baseline: StoredRun
    candidate: StoredRun
    rows: list[Row]  # the primary metric first


def compare(baseline: StoredRun, candidate: StoredRun, *, force: bool = False) -> Comparison:
    if not force:
        differ = [
            f"{name} {getattr(baseline, field)} and {getattr(candidate, field)}"
            for name, field in (("eval set", "evalset_hash"), ("split", "split"))
            if getattr(baseline, field) != getattr(candidate, field)
        ]
        if differ:
            raise NotComparable(
                f"runs {baseline.id} and {candidate.id} differ in {'; '.join(differ)}: their"
                " numbers do not measure the same thing (pass --force to compare anyway)"
            )
    queries = baseline.metrics.keys()
    if queries != candidate.metrics.keys():
        raise NotComparable(
            f"runs {baseline.id} and {candidate.id} hold different queries:"
            f" {len(queries - candidate.metrics.keys())} only in the baseline,"
            f" {len(candidate.metrics.keys() - queries)} only in the candidate. A stopped run is"
            " finished with `ragcalibrate run CONFIG --resume RUN_ID`"
        )
    if moved := [q for q in queries if baseline.document_of[q] != candidate.document_of[q]]:
        raise NotComparable(f"{len(moved)} queries belong to other documents in the two runs")

    def paired(metric: str) -> bool:
        return any(
            values.get(metric) is not None and candidate.metrics[query].get(metric) is not None
            for query, values in baseline.metrics.items()
        )

    # A metric that no query defines in both runs has no mean to show: it gets no row.
    names = list(dict.fromkeys(m for values in baseline.metrics.values() for m in values))
    names = [m for m in names if paired(m)]
    if PRIMARY not in names:
        raise NotComparable(f"the primary metric {PRIMARY} is not defined in both runs")
    names.remove(PRIMARY)
    rows = [_row(m, baseline, candidate) for m in [PRIMARY, *names]]
    return Comparison(baseline, candidate, rows)


def _row(metric: str, baseline: StoredRun, candidate: StoredRun) -> Row:
    # A query counts for a metric only if both runs define it there (eval-spec §3.1: undefined
    # is excluded, not zero). For answerable queries every retrieval metric is defined.
    base: dict[str, float] = {}
    cand: dict[str, float] = {}
    for query, values in baseline.metrics.items():
        b, c = values.get(metric), candidate.metrics[query].get(metric)
        if b is not None and c is not None:
            base[query], cand[query] = b, c
    n_documents = len({baseline.document_of[q] for q in base})
    interval = None
    if n_documents >= MIN_DOCUMENTS:
        interval = paired_cluster_bootstrap(cand, base, baseline.document_of, seed=SEED)
    n = len(base)
    outcome, note = _outcome(metric, baseline, candidate, interval, n_documents)
    return Row(
        metric=metric,
        baseline=math.fsum(base.values()) / n,
        candidate=math.fsum(cand.values()) / n,
        difference=math.fsum(cand[q] - base[q] for q in base) / n,
        interval=interval,
        n_queries=n,
        n_documents=n_documents,
        outcome=outcome,
        note=note,
    )


def _outcome(
    metric: str,
    baseline: StoredRun,
    candidate: StoredRun,
    interval: Interval | None,
    n_documents: int,
) -> tuple[Outcome | None, str]:
    if metric != PRIMARY:
        return None, "secondary, does not gate"
    if baseline.chunker_id != candidate.chunker_id:
        # eval-spec §3.4: recall@k rewards big chunks, so it cannot judge a chunker change. What
        # gates one instead is decision D8 in the plan, still open.
        return None, "no outcome: the chunkers differ, and recall@k favours bigger chunks (D8)"
    if interval is None:
        return Outcome.INCONCLUSIVE, f"{n_documents} documents, fewer than {MIN_DOCUMENTS} (F-003)"
    decision = decide(interval.lo, interval.hi, DELTA)
    return decision.outcome, "small regression detected" if decision.small_regression else ""


# Rendering. Both formats come from one list of blocks, so they cannot say different things.


class Text(NamedTuple):
    tag: str  # "h1", "h2" or "p"
    text: str


class Table(NamedTuple):
    header: list[str]
    rows: list[list[str]]


COLUMNS = ["metric", "baseline", "candidate", "delta", "95% CI", "outcome", "queries", "documents"]


def render_markdown(comparisons: Sequence[Comparison]) -> str:
    out: list[str] = []
    for block in _blocks(comparisons):
        if isinstance(block, Text):
            prefix = {"h1": "# ", "h2": "## ", "p": ""}[block.tag]
            out += [prefix + block.text, ""]
        else:
            for cells in [block.header, ["---"] * len(block.header), *block.rows]:
                out.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
            out.append("")
    return "\n".join(out)


def render_html(comparisons: Sequence[Comparison]) -> str:
    out = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        '<head><meta charset="utf-8"><title>Run comparison</title>',
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:80rem}"
        "table{border-collapse:collapse;margin-bottom:1.5rem}"
        "th,td{border:1px solid #ccc;padding:.25rem .5rem;text-align:left;"
        "font-variant-numeric:tabular-nums}</style>",
        "</head>",
        "<body>",
    ]
    for block in _blocks(comparisons):
        if isinstance(block, Text):
            out.append(f"<{block.tag}>{html.escape(block.text)}</{block.tag}>")
        else:
            out.append("<table>")
            out.append(_tr("th", block.header))
            out += [_tr("td", cells) for cells in block.rows]
            out.append("</table>")
    out += ["</body>", "</html>", ""]
    return "\n".join(out)


def _tr(tag: str, cells: list[str]) -> str:
    return "<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>"


def _blocks(comparisons: Sequence[Comparison]) -> list[Text | Table]:
    if not comparisons:
        raise ValueError("nothing to render: no comparisons")
    baseline = comparisons[0].baseline
    method = (
        f"Paired, document-clustered bootstrap: {N_RESAMPLES:,} resamples of documents,"
        f" percentile {CONFIDENCE:.0%} interval of the mean difference (candidate minus"
        f" baseline), seed {SEED}. The primary metric, {PRIMARY}, gates with delta = {DELTA}:"
        f" pass if the interval's lower end is at least -{DELTA}, fail if the whole interval is"
        f" below zero and reaches past -{DELTA}, inconclusive otherwise, and inconclusive with no"
        f" interval below {MIN_DOCUMENTS} documents (docs/eval-spec.md §6). The other metrics are"
        " shown and never gate. Means and differences are over the queries both runs define the"
        " metric for."
    )
    runs: list[list[str]] = [
        ["baseline" if i == 0 else f"candidate {i}", *_describe(r)]
        for i, r in enumerate([baseline, *(c.candidate for c in comparisons)])
    ]
    blocks: list[Text | Table] = [
        Text("h1", "Run comparison"),
        Text("p", method),
        Table(["role", "run", "split", "strategy", "chunker", "git", "eval set", "config"], runs),
    ]
    for i, comparison in enumerate(comparisons, start=1):
        c = comparison.candidate
        heading = (
            f"Candidate {i}: {c.strategy} ({c.id}) against {baseline.strategy} ({baseline.id})"
        )
        blocks.append(Text("h2", heading))
        blocks.append(Table(COLUMNS, [_cells(row) for row in comparison.rows]))
    return blocks


def _describe(run: StoredRun) -> list[str]:
    git = run.git_sha[:7] + (" (dirty)" if run.dirty else "")
    return [
        run.id,
        run.split,
        run.strategy,
        run.chunker_id,
        git,
        run.evalset_hash[:12],
        run.config_hash[:12],
    ]


def _cells(row: Row) -> list[str]:
    i = row.interval
    outcome = row.outcome.value if row.outcome is not None else ""
    return [
        row.metric + (" (primary)" if row.metric == PRIMARY else ""),
        f"{row.baseline:.4f}",
        f"{row.candidate:.4f}",
        f"{row.difference:+.4f}",
        "not computed" if i is None else f"[{i.lo:+.4f}, {i.hi:+.4f}]",
        ", ".join(part for part in (outcome, row.note) if part),
        f"{row.n_queries:,}",
        f"{row.n_documents:,}",
    ]
