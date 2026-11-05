.PHONY: up down test test-integration lint data evalsets models ingest serve gate

# Create .env from the example on first use; the values are local-development only.
.env:
	cp .env.example .env

# Start Postgres (pgvector) and wait until its healthcheck passes.
up: .env
	docker compose up -d --wait

down:
	docker compose down

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run pyright
	uv run lint-imports

test:
	uv run pytest tests/unit tests/property

# Needs Docker: each session starts its own throwaway pgvector container (testcontainers).
test-integration:
	uv run pytest tests/integration

# Download CUAD, pinned to a commit and verified by checksum (stdlib only).
data:
	uv run python -I scripts/fetch_cuad.py

# Generate evalsets/ from the pinned CUAD zip (deterministic; compare with evalsets/cuad.manifest.json).
evalsets: data
	uv run python scripts/build_evalsets.py

# Download the local models, each pinned to a commit and verified by sha256: the embedding model
# (bge-small-en-v1.5, 134 MB) and S4's cross-encoder (ms-marco-MiniLM-L6-v2, 91 MB).
models:
	uv run python -I scripts/fetch_models.py

# Load CUAD into Postgres (documents, chunks, embeddings). Needs `make up`. Idempotent and
# resumable; the first full run embeds every chunk on CPU, which takes several minutes.
# CHUNKER=c2 loads the structure-aware chunker next to C1 (plan step 3.4); SIZE sets the window
# in tokens (SIZE=199 is the size-matched C1 of plan step 3.9).
CHUNKER ?= c1
SIZE ?= 256
ingest: data models
	uv run alembic upgrade head
	uv run python scripts/ingest.py --chunker $(CHUNKER) --size $(SIZE)

# Run the RAG service (system under test) on 127.0.0.1:8000. Needs `make up` and `make ingest`.
serve:
	uv run uvicorn ragcalibrate.service.app:create_app --factory --host 127.0.0.1 --port 8000

# Gate the working tree against the merge base with BASE (plan step 4.7a): runs CONFIG on all of
# dev at both, compares, prints the report. Starts and stops its own services on ports 8101 and
# 8102. Needs `make up`, `make models`, `make ingest` and `make evalsets`. The script exits 0 on a
# Pass or no verdict, 1 on a Fail, 2 if it cannot run; make reports any non-zero as its own 2.
CONFIG ?= configs/s3-hybrid.yaml
BASE ?= main
gate:
	uv run python scripts/gate.py $(CONFIG) --base $(BASE)
