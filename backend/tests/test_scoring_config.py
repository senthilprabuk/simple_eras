import pytest
from sqlalchemy import text

from app.services.scoring_config import ScoringConfigError, validate_scoring_config


async def test_every_rule_in_the_approved_ruleset_is_accepted(db):
    rows = (await db.execute(text("""
        SELECT p.parameter_code, p.parameter_type, pp.scoring_config, sp.observation_days,
               coalesce((SELECT array_agg(o.option_code) FROM meta.parameter_option o
                         WHERE o.parameter_id = p.parameter_id), '{}') AS options
        FROM meta.procedure_parameter pp
        JOIN meta.parameter p ON p.parameter_id = pp.parameter_id
        JOIN meta.ruleset r ON r.ruleset_id = pp.ruleset_id
        JOIN meta.surgical_procedure sp ON sp.procedure_id = r.procedure_id
        WHERE sp.procedure_code = 'TKR' AND r.version = '1.0.0'
    """))).mappings().all()
    assert len(rows) == 12
    for row in rows:
        validate_scoring_config(row["scoring_config"], row["parameter_type"], row["options"], row["observation_days"])


FEVER = {"direction": "higher_is_worse", "bands": [[0, 37.5, 0], [37.5, 99, 3]]}
OXYGEN = {"direction": "higher_is_better", "bands": [[0, 95, 3], [95, 101, 0]]}
DROP = {"direction": "higher_is_better", "detector": "drop_from_personal_best", "drop_fraction": 0.5, "score": 2}


@pytest.mark.parametrize("config, kind, message", [
    ({"binary_score": 4}, "boolean", "from 0 to 3"),
    ({"binary_score": 2, "emergency": "yes"}, "boolean", "true or false"),
    ({"bands": [[0, 1, 0]]}, "boolean", "unknown setting bands"),
    ({"milestone": {"14": "sofa"}, "score": 1}, "ordinal", "'sofa' is not one of chair, car"),
    ({"milestone": {"99": "chair"}, "score": 1}, "ordinal", "from 0 to 84"),
    ({**DROP, "drop_fraction": 1.5}, "numeric", "between 0 and 1"),
    ({**DROP, "detector": "trend"}, "numeric", "the only detector"),
    ({}, "numeric", "JSON object"),
    ({**FEVER, "bands": [[0, "38", 0]]}, "numeric", "must be a number"),
])
def test_rules_are_checked_against_the_kind_of_measure(config, kind, message):
    with pytest.raises(ScoringConfigError, match=message):
        validate_scoring_config(config, kind, ["chair", "car", "bike"], 84)


@pytest.mark.parametrize("config, kind, message", [
    ({"bands": [[0, 37.5, 0], [37.5, 99, 3]]}, "numeric", "needs direction"),
    ({"direction": "up", "bands": [[0, 37.5, 0]]}, "numeric", "direction must be"),
    ({**FEVER, "direction": "higher_is_better"}, "numeric", "score at the high end, so direction is higher_is_worse"),
    ({**OXYGEN, "direction": "higher_is_worse"}, "numeric", "score at the low end, so direction is higher_is_better"),
    ({**DROP, "direction": "higher_is_worse"}, "numeric", "watches for a fall"),
    ({"direction": "higher_is_worse", "binary_score": 2}, "boolean", "unknown setting direction"),
    ({"direction": "higher_is_better", "milestone": {"14": "chair"}, "score": 1}, "ordinal", "unknown setting direction"),
])
def test_a_numeric_rule_must_say_which_way_it_goes_wrong(config, kind, message):
    with pytest.raises(ScoringConfigError, match=message):
        validate_scoring_config(config, kind, ["chair", "car", "bike"], 84)


@pytest.mark.parametrize("config", [
    FEVER,
    OXYGEN,
    DROP,
    # Bands scoring at both ends say nothing about which way is worse, so either is allowed.
    {"direction": "higher_is_worse", "bands": [[0, 60, 2], [60, 100, 0], [100, 999, 3]]},
    {"direction": "higher_is_better", "bands": [[0, 60, 2], [60, 100, 0], [100, 999, 3]]},
    {"direction": "higher_is_worse", "bands_by_day": {"0-3": [[0, 8, 0], [8, 99, 1]], "4-84": [[0, 4, 0], [4, 99, 2]]}},
])
def test_a_direction_that_matches_the_bands_is_accepted(config):
    validate_scoring_config(config, "numeric", [], 84)
