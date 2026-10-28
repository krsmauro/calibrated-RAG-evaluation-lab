"""Load CUAD into Postgres: documents, C1 chunks and bge-small embeddings (plan step 2.6).

Usage: make ingest   (applies migrations first; or: uv run python scripts/ingest.py)
Idempotent and resumable: a re-run skips what is stored, and an interrupted run continues
from the last committed document or batch. Embedding all 24,872 chunks on CPU takes minutes.
"""

import sys
import time
from pathlib import Path

import psycopg

from ragcalibrate.config import load_settings
from ragcalibrate.corpora.cuad import load_cuad
from ragcalibrate.ingest.chunkers import Chunk, c1_id, chunk_c1
from ragcalibrate.ingest.embedding import DEFAULT_MODEL_DIR, EMBEDDER_ID, Embedder, load_tokenizer
from ragcalibrate.ingest.load import count_offset_mismatches, counts, embed_chunks, ingest_documents
from ragcalibrate.logs import configure_logging

CUAD_ZIP = Path("data/raw/cuad/data.zip")
CORPUS = "cuad"
# Starting defaults chosen by the user on 2026-10-28 (plan step 2.4); tuned on dev only, later.
C1_SIZE, C1_OVERLAP = 256, 32
# ONNX Runtime was fastest at batch 16 (ADR 0011). A commit every 512 chunks is about 9 s of
# embedding, so an interruption repeats at most that much work.
EMBED_BATCH, COMMIT_EVERY = 16, 512


def main() -> int:
    configure_logging()
    settings = load_settings()
    data = load_cuad(CUAD_ZIP)
    tokenizer = load_tokenizer(DEFAULT_MODEL_DIR)
    chunker_id = c1_id(EMBEDDER_ID, C1_SIZE, C1_OVERLAP)

    def chunk(text: str) -> list[Chunk]:
        return chunk_c1(text, tokenizer, C1_SIZE, C1_OVERLAP)

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
