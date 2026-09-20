"""Unit tests for reading a ruleset's scoring config; no database."""

from app.services.scoring import band_threshold, bands_for_day, daily_thresholds, describe_scoring

TEMP = {"direction": "higher_is_worse", "bands": [[0, 37.5, 0], [37.5, 38.0, 1], [38.0, 38.5, 2], [38.5, 99, 3]]}
SPO2 = {"direction": "higher_is_better", "bands": [[0, 90, 3], [90, 93, 2], [93, 95, 1], [95, 101, 0]]}
PAIN = {"direction": "higher_is_worse", "bands_by_day": {
    "0-3": [[0, 8, 0], [8, 10, 1], [10, 99, 3]],
    "4-10": [[0, 4, 0], [4, 6, 1], [6, 8, 2], [8, 99, 3]],
    "11-84": [[0, 3, 0], [3, 5, 1], [5, 7, 2], [7, 99, 3]],
}}
STEPS = {"direction": "higher_is_better", "detector": "drop_from_personal_best", "drop_fraction": 0.5, "score": 2}


def test_threshold_is_where_a_quiet_low_end_starts_scoring():
    assert band_threshold(TEMP["bands"]) == (37.5, "above")


def test_threshold_for_bands_that_worry_when_low():
    assert band_threshold(SPO2["bands"]) == (95.0, "below")


def test_bands_that_never_score_have_no_threshold():
    assert band_threshold([[0, 99, 0]]) is None


def test_a_rule_scoring_at_both_ends_is_read_the_way_it_declares():
    """Blood pressure worries high and low; only the rule can say which end it watches."""
    both_ends = [[0, 60, 2], [60, 100, 0], [100, 999, 3]]
    assert band_threshold(both_ends, "higher_is_worse") == (100.0, "above")
    assert band_threshold(both_ends, "higher_is_better") == (60.0, "below")


def test_pain_threshold_tightens_as_recovery_progresses():
    assert bands_for_day(PAIN["bands_by_day"], 2)[1] == [8, 10, 1]
    thresholds, direction = daily_thresholds(PAIN, [2, 5, 15], [6, 3, 2], 0, 84)
    assert thresholds == [8.0, 4.0, 3.0]
    assert direction == "above"


def test_no_threshold_outside_the_scoring_window():
    thresholds, _ = daily_thresholds(TEMP, [0, 1, 2], [37.0, 37.1, 37.2], 1, 1)
    assert thresholds == [None, 37.5, None]


def test_steps_threshold_is_half_the_personal_best_so_far():
    thresholds, direction = daily_thresholds(STEPS, [0, 1, 2, 3], [100, 1200, None, 400], 0, 84)
    assert direction == "below"
    # No history on day 0; the best before each day sets the bar; a missed day does not reset it.
    assert thresholds == [None, 50.0, 600.0, 600.0]


def test_scoring_summaries_read_as_plain_rules():
    assert describe_scoring(TEMP) == "37.5–38 → 1, 38–38.5 → 2, ≥38.5 → 3"
    assert describe_scoring(SPO2) == "<90 → 3, 90–93 → 2, 93–95 → 1"
    assert describe_scoring({"binary_score": 3, "emergency": True}).startswith("Yes is an emergency")
    assert describe_scoring({"binary_score": 2}) == "Yes scores 2"
    assert describe_scoring(STEPS) == "Scores 2 when below 50% of the patient's personal best"
    assert "Days 0–3" in describe_scoring(PAIN)
    assert describe_scoring({"relative_to_baseline": True, "bands": [[0, 10, 0], [10, 20, 1]]}) == \
        "Rise above discharge baseline: 10–20 → 1"
    assert describe_scoring({"milestone": {"14": "chair"}, "score": 1}) == "Expected: chair by day 14; scores 1 when behind"
