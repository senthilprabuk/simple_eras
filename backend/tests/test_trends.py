"""
The five trend detectors, without a database.

Each is checked twice where it matters: once on a measure where higher is worse
and once where higher is better, since the only thing separating those two cases
is the rule's direction.
"""

import pytest

from app.services.trends import (
    Series,
    delta_vs_rolling_mean,
    drop_from_personal_best,
    monotonic_rise,
    reemergence,
    streak,
    worsening,
)

RISING_BANDS = [[0, 2, 0], [2, 3, 1], [3, 4, 2], [4, 99, 3]]


def series(direction, values, scores=None):
    return Series(direction=direction, values=values, scores=scores or {})


def test_direction_decides_which_way_is_the_wrong_way():
    assert worsening("higher_is_worse", 38.2, 37.0) == pytest.approx(1.2)
    assert worsening("higher_is_better", 91, 97) == pytest.approx(6)
    # A measure that improved has moved a negative distance the wrong way.
    assert worsening("higher_is_worse", 36.5, 37.0) == pytest.approx(-0.5)


# ------------------------------------------------- delta against a rolling mean

DELTA = {"detector": "delta_vs_rolling_mean", "window_days": 3, "min_observations": 3, "bands": RISING_BANDS}


def test_pain_is_scored_on_the_jump_from_its_own_average():
    pain = series("higher_is_worse", {6: 4, 7: 4, 8: 4, 9: 7})
    assert delta_vs_rolling_mean(pain, 9, DELTA) == 2  # delta 3 falls in [3,4)


def test_a_patient_who_is_simply_always_sore_raises_nothing():
    """Zero, not silence: three days of history is enough to say the gap was looked at and was fine."""
    steady = series("higher_is_worse", {6: 6, 7: 6, 8: 6, 9: 6})
    assert delta_vs_rolling_mean(steady, 9, DELTA) == 0


def test_the_same_detector_reads_a_falling_measure():
    oxygen = series("higher_is_better", {6: 97, 7: 97, 8: 97, 9: 93})
    assert delta_vs_rolling_mean(oxygen, 9, DELTA) == 3  # fallen 4 below its own average
    assert delta_vs_rolling_mean(series("higher_is_better", {6: 93, 7: 93, 8: 93, 9: 97}), 9, DELTA) is None


def test_a_detector_that_has_not_seen_enough_days_stays_silent():
    """Silence, not zero: zero would read as assessed and normal during warm-up."""
    assert delta_vs_rolling_mean(series("higher_is_worse", {8: 4, 9: 9}), 9, DELTA) is None
    assert delta_vs_rolling_mean(series("higher_is_worse", {6: 4, 7: 4, 8: 4}), 9, DELTA) is None


# --------------------------------------------------------------- reemergence

RETURNED = {"detector": "reemergence", "score": 3, "normal_days_required": 2}


def test_a_fever_that_settles_and_comes_back():
    settled = series("higher_is_worse", {}, {1: 2, 2: 0, 3: 0, 4: 0, 6: 1})
    assert reemergence(settled, 6, RETURNED) == 3


def test_a_first_fever_is_not_a_return_and_nor_is_one_that_never_settled():
    assert reemergence(series("higher_is_worse", {}, {4: 0, 5: 0, 6: 1}), 6, RETURNED) is None
    assert reemergence(series("higher_is_worse", {}, {4: 1, 5: 0, 6: 1}), 6, RETURNED) is None
    assert reemergence(series("higher_is_worse", {}, {4: 1, 5: 1, 6: 0}), 6, RETURNED) is None


# ------------------------------------------------------------- monotonic rise

CREEP = {"detector": "monotonic_rise", "score": 2, "window_days": 5, "min_observations": 3, "min_total_rise": 0.5}


def test_a_steady_climb_that_never_crosses_a_threshold():
    """Every reading here is below 37.5, so the bands see nothing at all."""
    creeping = series("higher_is_worse", {5: 36.6, 6: 36.9, 7: 37.1, 8: 37.2, 9: 37.4})
    assert monotonic_rise(creeping, 9, CREEP) == 2


def test_a_climb_that_turns_back_or_is_too_small_to_matter():
    assert monotonic_rise(series("higher_is_worse", {6: 36.6, 7: 37.2, 8: 36.9, 9: 37.4}), 9, CREEP) is None
    assert monotonic_rise(series("higher_is_worse", {7: 36.9, 8: 37.0, 9: 37.1}), 9, CREEP) is None


def test_a_steady_fall_is_the_climb_for_a_measure_where_higher_is_better():
    sinking = series("higher_is_better", {6: 97, 7: 96, 8: 95, 9: 94})
    assert monotonic_rise(sinking, 9, {**CREEP, "min_total_rise": 2}) == 2


# ------------------------------------------------- drop from a personal best

REGRESSION = {"detector": "drop_from_personal_best", "score": 2, "drop_fraction": 0.5}


def test_steps_below_half_the_patients_own_best():
    walker = series("higher_is_better", {5: 300, 6: 500, 7: 480, 9: 150})
    assert drop_from_personal_best(walker, 9, REGRESSION) == 2
    assert drop_from_personal_best(series("higher_is_better", {6: 500, 9: 400}), 9, REGRESSION) is None


def test_the_first_day_has_no_best_to_fall_from():
    assert drop_from_personal_best(series("higher_is_better", {0: 40}), 0, REGRESSION) is None


# ------------------------------------------------------------------- streak

PERSISTENT = {"detector": "streak", "score": 1, "min_days": 3}


def test_anything_abnormal_three_days_running():
    assert streak({7: True, 8: True, 9: True}, 9, PERSISTENT) == 1
    assert streak({7: True, 8: False, 9: True}, 9, PERSISTENT) is None


def test_a_skipped_day_breaks_the_run_because_it_is_unknown_not_normal():
    assert streak({7: True, 9: True}, 9, PERSISTENT) is None
