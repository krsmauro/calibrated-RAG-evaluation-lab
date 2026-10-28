.PHONY: up down test lint data evalsets

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

test:
	uv run pytest tests/unit tests/property

# Download CUAD, pinned to a commit and verified by checksum (stdlib only).
data:
	uv run python -I scripts/fetch_cuad.py

# Generate evalsets/ from the pinned CUAD zip (deterministic; compare with evalsets/cuad.manifest.json).
evalsets: data
	uv run python scripts/build_evalsets.py
