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


@pytest.mark.parametrize("config, kind, message", [
    ({"binary_score": 4}, "boolean", "from 0 to 3"),
    ({"binary_score": 2, "emergency": "yes"}, "boolean", "true or false"),
    ({"bands": [[0, 1, 0]]}, "boolean", "unknown setting bands"),
    ({"milestone": {"14": "sofa"}, "score": 1}, "ordinal", "'sofa' is not one of chair, car"),
    ({"milestone": {"99": "chair"}, "score": 1}, "ordinal", "from 0 to 84"),
    ({"detector": "drop_from_personal_best", "drop_fraction": 1.5, "score": 2}, "numeric", "between 0 and 1"),
    ({"detector": "trend", "score": 2}, "numeric", "the only detector"),
    ({}, "numeric", "JSON object"),
    ({"bands": [[0, "38", 0]]}, "numeric", "must be a number"),
])
def test_rules_are_checked_against_the_kind_of_measure(config, kind, message):
    with pytest.raises(ScoringConfigError, match=message):
        validate_scoring_config(config, kind, ["chair", "car", "bike"], 84)
