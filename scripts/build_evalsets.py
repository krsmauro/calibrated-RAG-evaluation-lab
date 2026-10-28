"""Generate evalsets/ from the pinned CUAD zip (plan step 2.3), or check the files on disk.

Usage: python -I scripts/build_evalsets.py [--check]
`--check` regenerates in memory and fails if the files on disk differ.
"""

import hashlib
import sys
from pathlib import Path

from ragcalibrate.corpora import evalsets
from ragcalibrate.corpora.cuad import load_cuad

ZIP = Path("data/raw/cuad/data.zip")
OUT = Path("evalsets")


def main() -> int:
    source = hashlib.sha256(ZIP.read_bytes()).hexdigest()
    files, manifest = evalsets.build(load_cuad(ZIP), source)
    if "--check" in sys.argv:
        on_disk = evalsets.verify(OUT)
        if on_disk != manifest:
            print("evalsets/ differs from what the pinned CUAD zip produces")
            return 1
        print(f"ok: evalsets/ matches the source (evalset_hash {manifest.evalset_hash[:12]}...)")
        return 0
    evalsets.write(OUT, files, manifest)
    print(f"wrote {len(files)} files, evalset_hash {manifest.evalset_hash}")
    for key, value in manifest.counts.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
