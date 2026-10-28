import os

from hypothesis import settings

# CI runs the same examples every time, so a red build reproduces; locally Hypothesis explores.
settings.register_profile("ci", derandomize=True, max_examples=200)
if os.environ.get("CI"):
    settings.load_profile("ci")
