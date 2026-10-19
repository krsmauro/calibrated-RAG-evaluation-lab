# Data licenses

The code in this repository is licensed under the MIT License (see `LICENSE`). The datasets it evaluates on are **not** covered by that license, are not committed to the repository, and keep their own licenses, listed here. Anything derived from a dataset and published from this repository (for example the files in `evalsets/`) carries the dataset's license and attribution.

## CUAD (Contract Understanding Atticus Dataset)

- **Creator:** The Atticus Project. Credit: *The Atticus Project, Contract Understanding Atticus Dataset (CUAD) v1.*
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0): <https://creativecommons.org/licenses/by/4.0/>
- **Source of the license statement:** the dataset's own page, <https://www.atticusprojectai.org/cuad>, which lists CC BY 4.0, and the dataset loader's license string on Hugging Face (`theatticusproject/cuad-qa`): "CUAD is licensed under the Creative Commons Attribution 4.0 (CC BY 4.0) license." The GitHub repository (<https://github.com/The-Atticus-Project/cuad>) contains no LICENSE file; the page above is the primary statement. Checked 2026-10-19.
- **Obtained from:** `data.zip` in the GitHub repository above, pinned to commit `7aad649183846688381a147eeb3601aff590fe4a` and verified by sha256 (`make data`, `scripts/fetch_cuad.py`).
- **Changes made:** none to the contract text. Derived files (queries, gold spans, split lists) reorganize the labels; they are not endorsed by The Atticus Project.
- **Paper:** Hendrycks, Burns, Chen and Ball, "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review", NeurIPS 2021 Datasets and Benchmarks, arXiv:2103.06268.
- The contracts are public filings from SEC EDGAR.

## QASPER

To be added in Phase 9, after its license is checked against the primary source (not from memory).
