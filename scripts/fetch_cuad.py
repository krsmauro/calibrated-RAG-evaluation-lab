"""Download CUAD data.zip, pinned to a commit, and verify its size and sha256.

Standard library only. The file is untrusted input: it is stored under data/raw/ (gitignored)
and later code reads members straight out of the zip instead of extracting it.
Usage: python -I scripts/fetch_cuad.py
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

# The Atticus Project renamed its GitHub org (old URLs redirect); this is the current name,
# pinned to the commit that last changed data.zip (2021-03-11) so the bytes cannot move.
COMMIT = "7aad649183846688381a147eeb3601aff590fe4a"
URL = f"https://raw.githubusercontent.com/The-Atticus-Project/cuad/{COMMIT}/data.zip"
SIZE = 18_309_308
SHA256 = "f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a"
DEST = Path("data/raw/cuad/data.zip")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not DEST.exists():
        DEST.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {URL}")
        with urllib.request.urlopen(URL, timeout=60) as response:
            DEST.write_bytes(response.read())
    if DEST.stat().st_size != SIZE or sha256(DEST) != SHA256:
        print(f"CHECKSUM MISMATCH for {DEST}: delete it and investigate before using it")
        return 1
    print(f"ok: {DEST} ({SIZE} bytes, sha256 {SHA256[:12]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
