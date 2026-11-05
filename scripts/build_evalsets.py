"""Generate evalsets/ from the pinned CUAD zip (plan step 2.3), or check the files on disk.

Usage: python -I scripts/build_evalsets.py [--check]
`--check` regenerates in memory and fails if the files on disk differ.

The CI subset (plan step 4.5) is drawn with CI_SIZE and CI_SEED below. To change its size,
change CI_SIZE and run `make evalsets`; `--check` compares the file with what these values draw.
"""

import hashlib
import sys
from pathlib import Path

from ragcalibrate.corpora import evalsets
from ragcalibrate.corpora.cuad import load_cuad

ZIP = Path("data/raw/cuad/data.zip")
OUT = Path("evalsets")
# Provisional until step 4.6's power study sets it. The cluster bootstrap under-covers below
# about 40 contracts (finding F-003); 60 leaves a margin and splits evenly into three strata.
CI_SIZE = 60
CI_SEED = 20261105


def main() -> int:
    source = hashlib.sha256(ZIP.read_bytes()).hexdigest()
    data = load_cuad(ZIP)
    files, manifest = evalsets.build(data, source)
    subset = evalsets.ci_subset(
        data, evalset_hash=manifest.evalset_hash, size=CI_SIZE, seed=CI_SEED
    )
    if "--check" in sys.argv:
        on_disk = evalsets.verify(OUT)
        if on_disk != manifest:
            print("evalsets/ differs from what the pinned CUAD zip produces")
            return 1
        if evalsets.read_ci_subset(OUT) != subset:
            print(f"{evalsets.CI_SUBSET} differs from what CI_SIZE and CI_SEED draw")
            return 1
        print(f"ok: evalsets/ matches the source (evalset_hash {manifest.evalset_hash[:12]}...)")
        print(f"ok: CI subset of {subset.size} (subset_hash {subset.subset_hash[:12]}...)")
        return 0
    evalsets.write(OUT, files, manifest)
    evalsets.write_ci_subset(OUT, subset)
    print(f"wrote {len(files)} files, evalset_hash {manifest.evalset_hash}")
    for key, value in manifest.counts.items():
        print(f"  {key}: {value}")
    print(
        f"wrote {evalsets.CI_SUBSET}: {subset.size} dev documents, seed {subset.seed},"
        f" subset_hash {subset.subset_hash}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
