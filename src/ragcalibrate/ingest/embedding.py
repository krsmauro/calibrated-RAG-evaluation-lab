"""Local embedding model: BAAI/bge-small-en-v1.5, run with ONNX Runtime on CPU (ADR 0011).

The model files come from the model's own Hugging Face repo, pinned to one commit and checked
by sha256 (`make models`); a silently updated model would change every retrieval result.
ONNX Runtime instead of sentence-transformers keeps PyTorch out of the install; the vectors
were checked against sentence-transformers once (ADR 0011 has the numbers).

`embed` is synchronous and CPU-bound on purpose: async callers must run it with
`asyncio.to_thread` so it never blocks the event loop (skill BE-CRITICAL-2).
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt
import onnxruntime as ort  # pyright: ignore[reportMissingTypeStubs] (ships partial inline types)
from tokenizers import Tokenizer

MODEL_REPO = "BAAI/bge-small-en-v1.5"
MODEL_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
# Recorded with every chunk embedding and run, so a model change is visible in the data.
EMBEDDER_ID = f"bge-small-en-v1.5@{MODEL_REVISION[:12]}"
DIMENSION = 384
# The model's context, including the [CLS] and [SEP] tokens it adds to every input.
MAX_TOKENS = 512
# path in the repo -> (size in bytes, sha256), read from the repo at MODEL_REVISION on 2026-10-28.
MODEL_FILES = {
    "tokenizer.json": (711_396, "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66"),
    "onnx/model.onnx": (
        133_093_490,
        "828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35",
    ),
}
DEFAULT_MODEL_DIR = Path("data/models/bge-small-en-v1.5")

Vectors = npt.NDArray[np.float32]


def load_tokenizer(model_dir: Path) -> Tokenizer:
    """The model's own tokenizer, with no truncation or padding (the chunker counts with it)."""
    return Tokenizer.from_file(str(model_dir / "tokenizer.json"))


class Embedder:
    """Load once (service lifespan or ingest entrypoint) and reuse; loading takes about a second."""

    def __init__(self, model_dir: Path = DEFAULT_MODEL_DIR, batch_size: int = 32) -> None:
        self.batch_size = batch_size
        self._tokenizer = load_tokenizer(model_dir)
        # Longer inputs are cut, not rejected. C1 chunks are far below this limit (step 2.4).
        # The two ignores: the tokenizers stubs leave **kwargs untyped.
        self._tokenizer.enable_truncation(MAX_TOKENS)  # pyright: ignore[reportUnknownMemberType]
        pad_id = self._tokenizer.token_to_id("[PAD]")
        self._tokenizer.enable_padding(pad_id=pad_id, pad_token="[PAD]")  # noqa: S106  # pyright: ignore[reportUnknownMemberType]
        self._session = ort.InferenceSession(
            str(model_dir / "onnx" / "model.onnx"), providers=["CPUExecutionProvider"]
        )

    def embed(self, texts: Sequence[str]) -> Vectors:
        """One unit-length float32 vector per text, shape (len(texts), DIMENSION).

        BGE pools by taking the [CLS] token's final hidden state, then L2-normalizes, so cosine
        similarity is a dot product.
        """
        step = self.batch_size
        batches = [self._embed_batch(texts[i : i + step]) for i in range(0, len(texts), step)]
        if not batches:
            return np.empty((0, DIMENSION), dtype=np.float32)
        return np.concatenate(batches)

    def _embed_batch(self, texts: Sequence[str]) -> Vectors:
        encodings = self._tokenizer.encode_batch(list(texts))
        feeds = {
            "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
            "token_type_ids": np.array([e.type_ids for e in encodings], dtype=np.int64),
        }
        # run() is typed as returning a union of output kinds; this model has one dense output,
        # (batch, sequence, DIMENSION), which asarray turns into a typed array.
        output = self._session.run(["last_hidden_state"], feeds)[0]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        hidden: Vectors = np.asarray(output, dtype=np.float32)  # pyright: ignore[reportUnknownArgumentType]
        cls = hidden[:, 0, :]
        return cls / np.linalg.norm(cls, axis=1, keepdims=True)
