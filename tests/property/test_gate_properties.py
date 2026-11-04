"""The gate's decision rule (plan step 4.3) on any interval: exactly one outcome, and the rule
never punishes a better candidate or a larger tolerance."""

from hypothesis import given
from hypothesis import strategies as st

from ragcalibrate.stats.gate import Outcome, decide

VALUE = st.floats(min_value=-1, max_value=1)
DELTA = st.floats(min_value=0, max_value=0.5)
RANK = {Outcome.FAIL: 0, Outcome.INCONCLUSIVE: 1, Outcome.PASS: 2}


@st.composite
def intervals(draw: st.DrawFn) -> tuple[float, float]:
    a, b = draw(VALUE), draw(VALUE)
    return min(a, b), max(a, b)


@given(intervals(), DELTA)
def test_exactly_one_condition_of_design_8_5_holds_and_it_is_the_outcome(
    interval: tuple[float, float], delta: float
) -> None:
    lo, hi = interval
    conditions = {
        Outcome.PASS: lo >= -delta,
        Outcome.FAIL: hi < 0 and lo < -delta,
        Outcome.INCONCLUSIVE: lo < -delta and hi >= 0,
    }
    assert sum(conditions.values()) == 1
    decision = decide(lo, hi, delta)
    assert conditions[decision.outcome]
    assert decision.small_regression == (decision.outcome is Outcome.PASS and hi < 0)


@given(intervals(), DELTA, st.floats(min_value=0, max_value=1))
def test_moving_the_interval_up_never_gives_a_worse_outcome(
    interval: tuple[float, float], delta: float, shift: float
) -> None:
    lo, hi = interval
    before = decide(lo, hi, delta).outcome
    after = decide(lo + shift, hi + shift, delta).outcome
    assert RANK[after] >= RANK[before]


@given(intervals(), DELTA, st.floats(min_value=0, max_value=0.5))
def test_a_larger_delta_never_gives_a_worse_outcome(
    interval: tuple[float, float], delta: float, more: float
) -> None:
    lo, hi = interval
    assert RANK[decide(lo, hi, delta + more).outcome] >= RANK[decide(lo, hi, delta).outcome]
