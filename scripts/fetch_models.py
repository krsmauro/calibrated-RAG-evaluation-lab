"""Download the local embedding model files, pinned to a Hugging Face commit, and verify them.

The pins (repo, commit, sizes, sha256) live in ragcalibrate.ingest.embedding so the code that
loads the model and the code that downloads it cannot disagree. Files go to data/models/
(gitignored). Idempotent: files already present and correct are not downloaded again.
Usage: python -I scripts/fetch_models.py
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

from ragcalibrate.ingest.embedding import DEFAULT_MODEL_DIR, MODEL_FILES, MODEL_REPO, MODEL_REVISION


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    for name, (size, digest) in MODEL_FILES.items():
        dest = DEFAULT_MODEL_DIR / name
        if not dest.exists():
            url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{name}"
            print(f"downloading {url}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            partial = dest.with_suffix(dest.suffix + ".part")
            with urllib.request.urlopen(url, timeout=120) as response:
                partial.write_bytes(response.read())
            partial.rename(dest)
        if dest.stat().st_size != size or sha256(dest) != digest:
            print(f"CHECKSUM MISMATCH for {dest}: delete it and investigate before using it")
            return 1
        print(f"ok: {dest} ({size} bytes, sha256 {digest[:12]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
