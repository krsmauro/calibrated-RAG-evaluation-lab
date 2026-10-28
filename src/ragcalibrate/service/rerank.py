"""S4's local cross-encoder: cross-encoder/ms-marco-MiniLM-L6-v2 on ONNX Runtime, CPU (ADR 0013).

The model files come from the model's own Hugging Face repo, pinned to one commit and checked
by sha256 (`make models`), as for the embedding model (ADR 0011).

`Reranker.score` is synchronous and CPU-bound on purpose: the service loads one `Reranker` in
its lifespan and calls `score` through `asyncio.to_thread`, so it never blocks the event loop
(skill BE-CRITICAL-2, BE-CRITICAL-3).
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import onnxruntime as ort  # pyright: ignore[reportMissingTypeStubs] (ships partial inline types)
from tokenizers import Tokenizer

from ragcalibrate.contract import RetrievedChunk

MODEL_REPO = "cross-encoder/ms-marco-MiniLM-L6-v2"
MODEL_REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
# Returned with every reranked response and recorded with the run.
RERANKER_ID = f"ms-marco-MiniLM-L6-v2@{MODEL_REVISION[:12]}"
# The model's context for the query and the passage together, special tokens included.
MAX_TOKENS = 512
# path in the repo -> (size in bytes, sha256), read from the repo at MODEL_REVISION on 2026-10-28.
MODEL_FILES = {
    "tokenizer.json": (711_396, "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66"),
    "onnx/model.onnx": (
        91_011_230,
        "5d3e70fd0c9ff14b9b5169a51e957b7a9c74897afd0a35ce4bd318150c1d4d4a",
    ),
}
DEFAULT_MODEL_DIR = Path("data/models/ms-marco-MiniLM-L6-v2")


class Reranker:
    """Load once (service lifespan) and reuse."""

    def __init__(self, model_dir: Path = DEFAULT_MODEL_DIR, batch_size: int = 32) -> None:
        self.batch_size = batch_size
        self._tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        # A pair longer than the context is cut, longest side first, as sentence-transformers
        # does. A CUAD question and a C1 chunk together stay far below it (ADR 0013).
        # The two ignores: the tokenizers stubs leave **kwargs untyped.
        self._tokenizer.enable_truncation(MAX_TOKENS)  # pyright: ignore[reportUnknownMemberType]
        pad_id = self._tokenizer.token_to_id("[PAD]")
        self._tokenizer.enable_padding(pad_id=pad_id, pad_token="[PAD]")  # noqa: S106  # pyright: ignore[reportUnknownMemberType]
        self._session = ort.InferenceSession(
            str(model_dir / "onnx" / "model.onnx"), providers=["CPUExecutionProvider"]
        )

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        """How relevant each text is to the query: the model's raw logit, higher is better.

        The model reads the query and the text together ("[CLS] query [SEP] text [SEP]"), so a
        score belongs to one pair. Its default activation is the identity: no sigmoid.
        """
        scores: list[float] = []
        for i in range(0, len(texts), self.batch_size):
            pairs = [(query, text) for text in texts[i : i + self.batch_size]]
            encodings = self._tokenizer.encode_batch(pairs)
            feeds = {
                "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
                "token_type_ids": np.array([e.type_ids for e in encodings], dtype=np.int64),
            }
            # One dense output, (batch, 1); asarray turns run()'s union type into a typed array.
            output = self._session.run(["logits"], feeds)[0]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            logits = np.asarray(output, dtype=np.float32)  # pyright: ignore[reportUnknownArgumentType]
            scores.extend(float(x) for x in logits[:, 0])
        return scores


def rerank(
    candidates: Sequence[RetrievedChunk], scores: Sequence[float], *, k: int
) -> list[RetrievedChunk]:
    """The k best candidates by the reranker's scores, best first, each with its new score.

    Equal scores are ordered by position in the document, then by chunk id, as every other
    strategy orders them, so the result never depends on the order of the candidates.
    """
    scored = sorted(
        zip(scores, candidates, strict=True),
        key=lambda item: (-item[0], item[1].start_char, item[1].chunk_id),
    )
    return [c.model_copy(update={"score": s}) for s, c in scored[:k]]
