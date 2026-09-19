import uuid

from sqlalchemy import text

from app.services.rules_engine import Binding, evaluate
from tests.conftest import login_headers
from tests.support import create_hospital


def _binding(code, kind, weight, config, window=(0, 84), unit=None):
    return Binding(0, code, code, kind, unit, weight, window[0], window[1], config)

# The approved TKR ruleset's configs.
TEMP = _binding("temp_c", "numeric", 3, {"bands": [[0, 37.5, 0], [37.5, 38.0, 1], [38.0, 38.5, 2], [38.5, 99, 3]]}, (0, 42), "C")
PAIN = _binding("pain", "numeric", 2, {"bands_by_day": {
    "0-3": [[0, 8, 0], [8, 10, 1], [10, 99, 3]],
    "4-10": [[0, 4, 0], [4, 6, 1], [6, 8, 2], [8, 99, 3]],
    "11-84": [[0, 3, 0], [3, 5, 1], [5, 7, 2], [7, 99, 3]],
}})
HR = _binding("hr", "numeric", 2, {"relative_to_baseline": True, "bands": [[0, 10, 0], [10, 20, 1], [20, 30, 2], [30, 999, 3]]})
SPO2 = _binding("spo2", "numeric", 2, {"bands": [[0, 90, 3], [90, 93, 2], [93, 95, 1], [95, 101, 0]]}, (0, 14))
BREATHLESS = _binding("breathless", "boolean", 3, {"binary_score": 3, "emergency": True}, (0, 42))
CALF = _binding("calf_pain", "boolean", 3, {"binary_score": 3}, (0, 42))
DRAINAGE = _binding("drainage", "boolean", 2, {"binary_score": 2}, (5, 28))
RULESET = [TEMP, PAIN, HR, SPO2, BREATHLESS, CALF, DRAINAGE]


def _run(answers, day=10, baselines=None):
    return evaluate(RULESET, answers, baselines or {}, day, review_at=5, critical_at=12, max_points=6)


def test_an_unremarkable_check_in_is_normal():
    result = _run({"temp_c": 36.8, "pain": 2, "breathless": False, "calf_pain": False})
    assert (result.tier, result.total_score, result.reasons, result.reason_key) == ("normal", 0, [], "none")


def test_emergency_answer_bypasses_scoring():
    result = _run({"breathless": True, "temp_c": 36.8})
    assert result.tier == "emergency" and result.is_override
    assert result.reasons[0]["detail"] == "breathless: yes (emergency)"


def test_red_flag_at_top_score_is_critical_and_emergency_still_wins():
    assert _run({"calf_pain": True}).tier == "critical"
    assert _run({"calf_pain": True, "breathless": True}).tier == "emergency"


def test_weighted_total_crosses_the_ruleset_cut_offs():
    assert _run({"temp_c": 38.2}).tier == "review"                               # 2 x 3 = 6
    mixed = _run({"temp_c": 38.6, "pain": 7})                                   # 9 capped to 6, + 2 x 2
    assert (mixed.tier, mixed.total_score) == ("review", 10)
    assert _run({"temp_c": 38.6, "pain": 7, "spo2": 88}).tier == "critical"     # + 6 = 16


def test_pulse_is_scored_against_the_discharge_baseline():
    result = _run({"hr": 100}, baselines={"hr": 76})
    assert result.total_score == 4 and "+24 from discharge" in result.reasons[0]["detail"]
    assert _run({"hr": 100}).total_score == 0  # no baseline, no score


def test_answers_outside_the_scoring_window_do_not_count():
    assert _run({"drainage": True}, day=2).total_score == 0
    assert _run({"drainage": True}, day=6).total_score == 4
    assert _run({"spo2": 80}, day=20).total_score == 0


def test_the_reported_breathless_check_in_would_have_been_an_emergency():
    # The day-21 submission that never reached the dashboard.
    result = _run({"temp_c": 45.0, "hr": 100, "spo2": 80, "pain": 3, "breathless": True}, day=21, baselines={"hr": 76})
    assert result.tier == "emergency"
    assert {r["name"] for r in result.reasons} == {"temp_c", "hr", "pain", "breathless"}  # spo2 unscored after day 14


def test_reason_key_depends_on_the_reasons_not_their_order():
    a = evaluate([TEMP, PAIN], {"temp_c": 39, "pain": 9}, {}, 10, 5, 12, 6)
    b = evaluate([PAIN, TEMP], {"temp_c": 39, "pain": 9}, {}, 10, 5, 12, 6)
    assert a.reason_key == b.reason_key != _run({"temp_c": 39}).reason_key


async def _setup(client, db):
    h = await create_hospital(db, f"ENG-{uuid.uuid4().hex[:6]}")
    headers = await login_headers(client, h.email, h.password)
    form = (await client.get(f"/api/v1/checkin/form?episode_id={h.episode_id}")).json()
    ids = {p["code"]: p["parameter_id"] for s in form["sections"] for p in s["parameters"]}

    def submit(key, values):
        return client.post("/api/v1/checkin", json={
            "episode_id": str(h.episode_id), "day_after_discharge": form["effective_day"], "simulated": False,
            "idempotency_key": key, "values": [{"parameter_id": ids[c], **v} for c, v in values.items()],
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


async def test_every_submission_is_evaluated_even_when_normal(client, db):
    h, headers, submit = await _setup(client, db)
    body = (await submit("engine-normal-1", {"temp_c": {"value_num": 36.8}, "breathless": {"value_bool": False}})).json()
    assert (body["tier"], body["alert_id"]) == ("normal", None)
    stored = (await db.execute(
        text("SELECT tier, reason_key FROM txn.check_in_evaluation WHERE check_in_id = :c"), {"c": body["check_in_id"]}
    )).one()
    assert tuple(stored) == ("normal", "none")
    assert await _queue(client, headers) == []
