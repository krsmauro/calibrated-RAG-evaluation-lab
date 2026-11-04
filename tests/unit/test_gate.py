"""The gate's decision rule (plan step 4.3): every outcome, every boundary, written out by hand."""

import pytest

from ragcalibrate.stats.gate import Decision, Outcome, decide

PASS, FAIL, INCONCLUSIVE = Outcome.PASS, Outcome.FAIL, Outcome.INCONCLUSIVE


@pytest.mark.parametrize(
    ("lo", "hi", "delta", "outcome", "small_regression"),
    [
        # Pass: lo >= -delta.
        (0.01, 0.02, 0.02, PASS, False),  # an improvement
        (-0.01, 0.03, 0.02, PASS, False),  # spans zero, regression under delta
        (-0.02, 0.03, 0.02, PASS, False),  # lo exactly at -delta passes
        (-0.01, 0.0, 0.02, PASS, False),  # hi exactly 0 is not below zero: no note
        (0.0, 0.0, 0.02, PASS, False),
        (-0.015, -0.005, 0.02, PASS, True),  # wholly below zero, above -delta: noted
        (-0.02, -0.001, 0.02, PASS, True),
        (-0.02, -0.02, 0.02, PASS, True),  # zero width at -delta
        # Fail: lo < -delta and hi < 0.
        (-0.03, -0.01, 0.02, FAIL, False),
        (-0.05, -0.0001, 0.02, FAIL, False),
        (-0.021, -0.021, 0.02, FAIL, False),  # zero width just past -delta
        # Inconclusive: lo < -delta and hi >= 0.
        (-0.03, 0.0, 0.02, INCONCLUSIVE, False),  # hi exactly 0
        (-0.03, 0.01, 0.02, INCONCLUSIVE, False),
        (-0.5, 0.5, 0.02, INCONCLUSIVE, False),
        # delta 0: any regression that can be detected blocks.
        (0.0, 0.01, 0.0, PASS, False),
        (-0.001, 0.01, 0.0, INCONCLUSIVE, False),
        (-0.01, -0.001, 0.0, FAIL, False),
    ],
)
def test_every_outcome_and_boundary(
    lo: float, hi: float, delta: float, outcome: Outcome, small_regression: bool
) -> None:
    assert decide(lo, hi, delta) == Decision(outcome, small_regression)


@pytest.mark.parametrize(
    ("lo", "hi", "delta", "message"),
    [
        (0.02, 0.01, 0.02, "not an interval"),
        (-0.01, 0.01, -0.02, "at least 0"),
        (float("nan"), 0.01, 0.02, "finite"),
        (-0.01, float("inf"), 0.02, "finite"),
    ],
)
def test_input_that_is_not_an_interval_is_refused(
    lo: float, hi: float, delta: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        decide(lo, hi, delta)


def test_outcomes_read_as_words_in_a_report() -> None:
    assert [str(o) for o in Outcome] == ["pass", "fail", "inconclusive"]
