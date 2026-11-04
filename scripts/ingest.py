"""Load CUAD into Postgres: documents, chunks and bge-small embeddings (plan steps 2.6, 3.4).

Usage: make ingest [CHUNKER=c2]   (applies migrations first; or:
       uv run python scripts/ingest.py [--chunker c1|c2])
Idempotent and resumable: a re-run skips what is stored, and an interrupted run continues
from the last committed document or batch. Each chunker's chunks are stored under its own id,
next to the other's. Embedding all of a chunker's chunks (about 25,000 to 30,000) on CPU takes
minutes.
"""

import argparse
import sys
import time
from pathlib import Path

import psycopg

from ragcalibrate.config import load_settings
from ragcalibrate.corpora.cuad import load_cuad
from ragcalibrate.ingest.chunkers import Chunk, c1_id, c2_id, chunk_c1, chunk_c2
from ragcalibrate.ingest.embedding import DEFAULT_MODEL_DIR, EMBEDDER_ID, Embedder, load_tokenizer
from ragcalibrate.ingest.load import count_offset_mismatches, counts, embed_chunks, ingest_documents
from ragcalibrate.logs import configure_logging

CUAD_ZIP = Path("data/raw/cuad/data.zip")
CORPUS = "cuad"
# Starting defaults chosen by the user on 2026-10-28 (plan step 2.4); tuned on dev only, later.
# C2 uses the same window, and C1's overlap inside the sections it falls back on (step 3.4).
SIZE, OVERLAP = 256, 32
CHUNKERS = {"c1": (c1_id, chunk_c1), "c2": (c2_id, chunk_c2)}
# ONNX Runtime was fastest at batch 16 (ADR 0011). A commit every 512 chunks is about 9 s of
# embedding, so an interruption repeats at most that much work.
EMBED_BATCH, COMMIT_EVERY = 16, 512


def main() -> int:
    parser = argparse.ArgumentParser(description="Load CUAD into Postgres.")
    parser.add_argument("--chunker", choices=sorted(CHUNKERS), default="c1")
    args = parser.parse_args()
    configure_logging()
    settings = load_settings()
    data = load_cuad(CUAD_ZIP)
    tokenizer = load_tokenizer(DEFAULT_MODEL_DIR)
    make_id, chunk_text = CHUNKERS[args.chunker]
    chunker_id = make_id(EMBEDDER_ID, SIZE, OVERLAP)

    def chunk(text: str) -> list[Chunk]:
        return chunk_text(text, tokenizer, SIZE, OVERLAP)

    url = settings.database_url.get_secret_value()
    with psycopg.connect(url, autocommit=True) as conn:
        started = time.perf_counter()
        chunked = ingest_documents(conn, CORPUS, data.documents, chunker_id, chunk)
        mismatches = count_offset_mismatches(conn, CORPUS, chunker_id)
        if mismatches:
            print(f"FAILED: {mismatches} chunks differ from their document's text at their offsets")
            return 1
        loaded = time.perf_counter()
        embedder = Embedder(DEFAULT_MODEL_DIR, batch_size=EMBED_BATCH)
        embedded = embed_chunks(conn, chunker_id, EMBEDDER_ID, embedder.embed, COMMIT_EVERY)
        finished = time.perf_counter()
        stored = counts(conn, CORPUS, chunker_id, EMBEDDER_ID)

    print(f"chunker  {chunker_id}\nembedder {EMBEDDER_ID}")
    print(f"this run: {chunked} documents chunked in {loaded - started:.1f} s (offsets checked),")
    print(f"          {embedded} chunks embedded in {finished - loaded:.1f} s")
    print(
        f"stored:   {stored.documents} documents, {stored.chunks} chunks, "
        f"{stored.embeddings} embeddings"
    )
    if stored.embeddings != stored.chunks:
        print("FAILED: not every chunk has an embedding")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
