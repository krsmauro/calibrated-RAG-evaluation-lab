"""The gate's decision rule (plan step 4.3; Design §8.5; skill STAT-CRITICAL-2).

With [lo, hi] the 95% interval of candidate minus baseline on the primary metric, and delta the
smallest regression worth blocking:

    Pass          lo >= -delta              any regression is smaller than delta
    Fail          lo < -delta and hi < 0    confidently worse, and delta cannot be ruled out
    Inconclusive  lo < -delta and hi >= 0   the eval set is too small to tell

The three cover every interval, and exactly one applies. A Pass whose interval lies wholly below
zero is a regression smaller than delta, detected: it passes with a note, never as a fourth
outcome. Under a true null, Fail needs the upper bound below zero, so the nominal false-fail
rate is about 2.5%; plan step 4.6 measures whether that holds.
"""

import math
from enum import StrEnum
from typing import NamedTuple


class Outcome(StrEnum):
    PASS = "pass"  # noqa: S105 (an outcome, not a password)
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class Decision(NamedTuple):
    outcome: Outcome
    small_regression: bool  # Pass with hi < 0: report "small regression detected"


def decide(lo: float, hi: float, delta: float) -> Decision:
    if not all(math.isfinite(x) for x in (lo, hi, delta)):
        raise ValueError(f"lo, hi and delta must be finite numbers: {lo}, {hi}, {delta}")
    if lo > hi:
        raise ValueError(f"not an interval: lo {lo} is above hi {hi}")
    if delta < 0:
        raise ValueError(f"delta is the size of a regression, at least 0, not {delta}")
    if lo >= -delta:
        return Decision(Outcome.PASS, small_regression=hi < 0)
    if hi < 0:
        return Decision(Outcome.FAIL, small_regression=False)
    return Decision(Outcome.INCONCLUSIVE, small_regression=False)
