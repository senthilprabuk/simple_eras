import uuid

from sqlalchemy import text

from app.services.rules_engine import Binding, Reading, RuleSet, Window, evaluate
from tests.conftest import login_headers
from tests.support import create_hospital


def _binding(code, kind, weight, config, window=(0, 84), unit=None, ranks=None):
    return Binding(0, code, code, kind, unit, weight, window[0], window[1], config, ranks or {})


WORSE_HIGH = {"direction": "higher_is_worse"}

# The approved TKR ruleset's configs.
TEMP = _binding("temp_c", "numeric", 3, {**WORSE_HIGH, "bands": [[0, 37.5, 0], [37.5, 38.0, 1], [38.0, 38.5, 2], [38.5, 99, 3]]}, (0, 42), "C")
PAIN = _binding("pain", "numeric", 2, {**WORSE_HIGH, "bands_by_day": {
    "0-3": [[0, 8, 0], [8, 10, 1], [10, 99, 3]],
    "4-10": [[0, 4, 0], [4, 6, 1], [6, 8, 2], [8, 99, 3]],
    "11-84": [[0, 3, 0], [3, 5, 1], [5, 7, 2], [7, 99, 3]],
}})
HR = _binding("hr", "numeric", 2, {**WORSE_HIGH, "relative_to_baseline": True,
                                   "bands": [[0, 10, 0], [10, 20, 1], [20, 30, 2], [30, 999, 3]]})
SPO2 = _binding("spo2", "numeric", 2, {"direction": "higher_is_better",
                                       "bands": [[0, 90, 3], [90, 93, 2], [93, 95, 1], [95, 101, 0]]}, (0, 14))
BREATHLESS = _binding("breathless", "boolean", 3, {"binary_score": 3, "emergency": True}, (0, 42))
CALF = _binding("calf_pain", "boolean", 3, {"binary_score": 3}, (0, 42))
DRAINAGE = _binding("drainage", "boolean", 2, {"binary_score": 2}, (5, 28))
KNEE = _binding("knee_bend", "ordinal", 1, {"milestone": {"14": "chair", "42": "car"}, "score": 2}, (14, 84),
                ranks={"chair": 1, "car": 2, "bike": 3})
RULESET = [TEMP, PAIN, HR, SPO2, BREATHLESS, CALF, DRAINAGE, KNEE]


def _run(answers, day=10, baselines=None, bindings=None, history=None, observed=(), composite=None, asked=()):
    ruleset = RuleSet(bindings=bindings or RULESET, review_at=5, critical_at=12,
                      max_points_per_parameter=6, composite=composite or {})
    window = Window(values=history or {}, observed_days=tuple(observed), baselines=baselines or {})
    return evaluate(Reading(day=day, answers=answers, asked=asked), window, ruleset)


def _points(result):
    return {r["name"]: r["points"] for r in result.reasons}


# ------------------------------------------------------------------ thresholds

def test_an_unremarkable_check_in_is_normal():
    result = _run({"temp_c": 36.8, "pain": 2, "breathless": False, "calf_pain": False})
    assert (result.tier, result.total_score, result.reasons, result.reason_key) == ("normal", 0, [], "none")


def test_emergency_answer_bypasses_scoring():
    result = _run({"breathless": True, "temp_c": 36.8})
    assert result.tier == "emergency" and result.is_override
    assert result.reasons[0]["detail"] == "breathless: yes (emergency)"


def test_any_signal_at_the_top_band_is_critical_on_its_own():
    """Declarative: binary_score 3 and a band 3 are how a rule says it is sufficient alone."""
    assert _run({"calf_pain": True}).tier == "critical"
    assert _run({"temp_c": 38.6}).tier == "critical"       # band 3 on its own, total only 6
    assert _run({"calf_pain": True, "breathless": True}).tier == "emergency"


def test_weighted_total_crosses_the_ruleset_cut_offs():
    assert _run({"temp_c": 38.2}).tier == "review"                          # band 2 x 3 = 6
    mixed = _run({"temp_c": 38.2, "pain": 7})                               # 6 + (band 2 x 2)
    assert (mixed.tier, mixed.total_score) == ("review", 10)
    assert _run({"temp_c": 38.2, "pain": 7, "spo2": 91}).tier == "critical"  # + 4 = 14


def test_pulse_is_scored_against_the_discharge_baseline():
    result = _run({"hr": 100}, baselines={"hr": 76})
    assert result.total_score == 4 and "+24 from discharge" in result.reasons[0]["detail"]
    assert _run({"hr": 100}).total_score == 0  # no baseline, no score


def test_a_falling_measure_is_read_against_its_baseline_the_other_way_round():
    """Same band list, opposite direction: the rule says which way the delta runs."""
    falling = _binding("spo2", "numeric", 2, {"direction": "higher_is_better", "relative_to_baseline": True,
                                              "bands": [[0, 2, 0], [2, 4, 1], [4, 99, 2]]}, unit="%")
    dropped = _run({"spo2": 92}, bindings=[falling], baselines={"spo2": 97})
    assert dropped.total_score == 4 and "-5 from discharge" in dropped.reasons[0]["detail"]
    assert _run({"spo2": 99}, bindings=[falling], baselines={"spo2": 97}).total_score == 0


def test_answers_outside_the_scoring_window_do_not_count():
    assert _run({"drainage": True}, day=2).total_score == 0
    assert _run({"drainage": True}, day=6).total_score == 4
    assert _run({"spo2": 80}, day=20).total_score == 0


def test_a_milestone_scores_only_when_the_patient_is_behind():
    assert _run({"knee_bend": "chair"}, day=42).total_score == 2   # car expected by day 42
    assert _run({"knee_bend": "car"}, day=42).total_score == 0
    assert _run({"knee_bend": "chair"}, day=20).total_score == 0   # only chair expected yet


def test_a_reading_no_band_covers_produces_silence_rather_than_a_zero():
    """The most dangerous config error there is, so the engine refuses to call it normal."""
    off_by_one = _binding("pain", "numeric", 2, {**WORSE_HIGH, "bands": [[0, 9, 0], [9, 10, 3]]})
    assert _run({"pain": 10}, bindings=[off_by_one]).reasons == []


def test_missing_answers_are_never_scored_and_thin_days_are_low_confidence():
    result = _run({"temp_c": 36.8}, asked=("temp_c", "pain", "breathless", "calf_pain"))
    assert (result.coverage, result.is_low_confidence) == (0.25, True)
    assert _run({"temp_c": 36.8, "pain": 1, "breathless": False}, asked=("temp_c", "pain", "breathless")).is_low_confidence is False


def test_reason_key_depends_on_the_reasons_not_their_order():
    a = _run({"temp_c": 38.2, "pain": 9}, bindings=[TEMP, PAIN])
    b = _run({"temp_c": 38.2, "pain": 9}, bindings=[PAIN, TEMP])
    assert a.reason_key == b.reason_key != _run({"temp_c": 38.2}).reason_key


# ---------------------------------------------------------------------- trends

RISING = {"name": "pain_rising", "detector": "delta_vs_rolling_mean", "weight": 2,
          "window_days": 3, "min_observations": 3, "bands": [[0, 2, 0], [2, 3, 1], [3, 4, 2], [4, 99, 3]]}
PAIN_WITH_TREND = _binding("pain", "numeric", 2, {**PAIN.config, "trends": [RISING]})

REGRESSION = {"name": "mobility_regression", "detector": "drop_from_personal_best",
              "weight": 1, "score": 2, "drop_fraction": 0.5}
STEPS = _binding("steps", "numeric", 1, {"direction": "higher_is_better", "trends": [REGRESSION]})

RETURNED = {"name": "fever_returned", "detector": "reemergence", "weight": 3, "score": 3, "normal_days_required": 2}
TEMP_WITH_TREND = _binding("temp_c", "numeric", 3, {**TEMP.config, "trends": [RETURNED]}, (0, 42), "C")

PERSISTENT = {"trends": [{"name": "persistent_abnormal", "detector": "streak", "weight": 1, "score": 1, "min_days": 3}]}


def test_a_trend_signal_is_named_separately_from_the_measure_it_reads():
    """One measure, two signals: the nurse sees both, and the cap keys on the measure."""
    history = {"pain": {5: 3, 6: 3, 7: 3, 8: 6}}
    result = _run({"pain": 7}, day=9, bindings=[PAIN_WITH_TREND], history=history, observed=(5, 6, 7, 8))
    assert sorted(_points(result)) == ["pain", "pain_rising"]
    assert "own 3-day average" in dict((r["name"], r["detail"]) for r in result.reasons)["pain_rising"]


def test_a_trend_must_hold_for_two_days_before_it_can_raise_the_tier():
    """A trend state persists for days and would otherwise flap across a band boundary."""
    jumped_once = {"pain": {6: 4, 7: 4, 8: 4}}
    held = {"pain": {5: 3, 6: 3, 7: 3, 8: 6}}
    assert _points(_run({"pain": 7}, day=9, bindings=[PAIN_WITH_TREND], history=jumped_once, observed=(6, 7, 8))) == {"pain": 4}
    assert "pain_rising" in _points(_run({"pain": 7}, day=9, bindings=[PAIN_WITH_TREND], history=held, observed=(5, 6, 7, 8)))


def test_a_trend_at_the_top_band_overrides_without_waiting_for_confirmation():
    settled = {"temp_c": {1: 38.2, 2: 37.0, 3: 37.0, 4: 37.0}}
    result = _run({"temp_c": 37.6}, day=5, bindings=[TEMP_WITH_TREND], history=settled, observed=(1, 2, 3, 4))
    assert result.tier == "critical" and result.is_override
    assert "fever_returned" in _points(result)


def test_a_cross_measure_signal_sees_what_no_single_measure_does():
    grumbling = {"temp_c": {6: 37.6, 7: 37.6, 8: 37.6}}
    result = _run({"temp_c": 37.6}, day=9, bindings=[TEMP], history=grumbling, observed=(6, 7, 8), composite=PERSISTENT)
    assert _points(result) == {"temp_c": 3, "persistent_abnormal": 1}


def test_the_older_lone_detector_shape_still_scores():
    """Rulesets approved before trends existed keep reading, with the measure's own weight."""
    legacy = _binding("steps", "numeric", 1, {"direction": "higher_is_better", "detector": "drop_from_personal_best",
                                              "drop_fraction": 0.5, "score": 2})
    history = {"steps": {5: 300, 6: 500, 7: 480, 8: 200}}
    assert _points(_run({"steps": 150}, day=9, bindings=[legacy], history=history, observed=(5, 6, 7, 8))) == {"steps": 2}


# ------------------------------------------------- the specification's examples

REDNESS = _binding("redness", "boolean", 3, {"binary_score": 2}, (0, 42))
SPEC_RULESET = [TEMP, PAIN_WITH_TREND, HR, REDNESS, STEPS]

# Pain climbs before day 9 and steps have already halved, so both trends have
# held for two days and count. Without that the tier is the same but four points
# lighter, which is what hysteresis costs.
SPEC_HISTORY = {"pain": {5: 3, 6: 3, 7: 3, 8: 6}, "steps": {5: 300, 6: 500, 7: 480, 8: 200}}


def test_worked_example_the_combination_case_on_day_nine():
    """Day 9. Pain 7 on a three-day mean of 4, 37.8, pulse 96 on a baseline of 70,
    redness spreading, steps down from a personal best of 500 to 150."""
    result = _run(
        {"pain": 7, "temp_c": 37.8, "hr": 96, "redness": True, "steps": 150},
        day=9, bindings=SPEC_RULESET, baselines={"hr": 70}, history=SPEC_HISTORY, observed=(5, 6, 7, 8),
    )
    assert _points(result) == {
        "pain": 4, "pain_rising": 2,      # 8 between them, capped to 6
        "temp_c": 3, "hr": 4, "redness": 6, "mobility_regression": 2,
    }
    assert (result.total_score, result.tier, result.is_override) == (21, "critical", False)
    # No signal reached the top band: this is the case a pure override model cannot see.
    assert max(r["score"] for r in result.reasons) == 2


def test_worked_example_the_same_readings_seven_days_earlier():
    """The same numbers on day 2 are normal, because the corridor and the trends differ."""
    result = _run(
        {"pain": 7, "temp_c": 37.8},
        day=2, bindings=SPEC_RULESET, history={"pain": {0: 9, 1: 8}}, observed=(0, 1),
    )
    assert _points(result) == {"temp_c": 3}
    assert (result.total_score, result.tier) == (3, "normal")


def test_no_measure_can_carry_the_composite_on_its_own():
    history = {"pain": {5: 3, 6: 3, 7: 3, 8: 6}}
    result = _run({"pain": 7}, day=9, bindings=[PAIN_WITH_TREND], history=history, observed=(5, 6, 7, 8))
    assert result.total_score == 6  # 4 + 4, capped at max_points_per_parameter


# ------------------------------------------------------------- through the API

async def _setup(client, db):
    h = await create_hospital(db, f"ENG-{uuid.uuid4().hex[:6]}")
    headers = await login_headers(client, h.email, h.password)
    form = (await client.get(f"/api/v1/checkin/form?episode_id={h.episode_id}")).json()
    ids = {p["code"]: p["parameter_id"] for s in form["sections"] for p in s["parameters"]}

    def submit(key, values, day=None):
        return client.post("/api/v1/checkin", json={
            "episode_id": str(h.episode_id), "day_after_discharge": form["effective_day"] if day is None else day,
            "simulated": False, "idempotency_key": key,
            "values": [{"parameter_id": ids[c], **v} for c, v in values.items()],
        })
    return h, headers, submit


async def _queue(client, headers):
    return (await client.get("/api/v1/dashboard/queue", headers=headers)).json()["items"]


async def test_emergency_check_in_reaches_the_dashboard_and_survives_a_correction(client, db):
    _, headers, submit = await _setup(client, db)

    first = (await submit("engine-emergency-1", {"breathless": {"value_bool": True}, "temp_c": {"value_num": 38.9}})).json()
    assert first["tier"] == "emergency" and first["alert_id"]
    queue = await _queue(client, headers)
    assert [(i["tier"], i["alert_id"]) for i in queue] == [("emergency", first["alert_id"])]
    assert any("emergency" in r["detail"] for r in queue[0]["reasons"])

    # A same-day correction supersedes the check-in but must not erase the alert.
    correction = (await submit("engine-emergency-2", {"breathless": {"value_bool": False}})).json()
    assert (correction["superseded_count"], correction["tier"], correction["alert_id"]) == (1, "normal", None)

    replay = (await submit("engine-emergency-1", {"breathless": {"value_bool": True}})).json()
    assert replay["duplicate"] is True and replay["alert_id"] is None

    assert [i["alert_id"] for i in await _queue(client, headers)] == [first["alert_id"]]


async def test_the_same_problem_reported_again_does_not_stack_alerts(client, db):
    _, headers, submit = await _setup(client, db)
    first = (await submit("engine-calf-1", {"calf_pain": {"value_bool": True}})).json()
    again = (await submit("engine-calf-2", {"calf_pain": {"value_bool": True}})).json()
    assert first["tier"] == again["tier"] == "critical"
    assert first["alert_id"] and again["alert_id"] is None
    assert len(await _queue(client, headers)) == 1


async def test_a_worsening_report_raises_the_alert_already_in_the_queue(client, db):
    """The same reason set getting worse escalates in place rather than queueing twice."""
    _, headers, submit = await _setup(client, db)
    first = (await submit("engine-worse-1", {"temp_c": {"value_num": 38.2}})).json()
    assert first["tier"] == "review"
    worse = (await submit("engine-worse-2", {"temp_c": {"value_num": 38.9}})).json()
    assert (worse["tier"], worse["alert_id"]) == ("critical", first["alert_id"])
    assert [(i["tier"], i["alert_id"]) for i in await _queue(client, headers)] == [("critical", first["alert_id"])]


async def test_every_submission_is_evaluated_even_when_normal(client, db):
    h, headers, submit = await _setup(client, db)
    body = (await submit("engine-normal-1", {"temp_c": {"value_num": 36.8}, "breathless": {"value_bool": False}})).json()
    assert (body["tier"], body["alert_id"]) == ("normal", None)
    stored = (await db.execute(
        text("SELECT tier, reason_key, coverage FROM txn.check_in_evaluation WHERE check_in_id = :c"),
        {"c": body["check_in_id"]},
    )).one()
    assert (stored[0], stored[1]) == ("normal", "none")
    assert stored[2] is not None  # coverage is recorded on every evaluation
    assert await _queue(client, headers) == []
