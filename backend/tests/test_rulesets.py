from tests.conftest import login_headers
from tests.support import create_hospital


async def test_lists_the_approved_ruleset_for_offered_procedures(client, nurse_headers):
    rulesets = (await client.get("/api/v1/rulesets", headers=nurse_headers)).json()
    assert len(rulesets) == 1
    tkr = rulesets[0]
    assert (tkr["procedure_code"], tkr["version"], tkr["status"]) == ("TKR", "1.0.0", "approved")
    assert (tkr["review_at"], tkr["critical_at"]) == (5, 12)
    assert tkr["parameter_count"] == 12
    assert tkr["episodes_using"] == 12


async def test_detail_explains_every_parameter_and_its_windows(client, nurse_headers):
    ruleset_id = (await client.get("/api/v1/rulesets", headers=nurse_headers)).json()[0]["ruleset_id"]
    detail = (await client.get(f"/api/v1/rulesets/{ruleset_id}", headers=nurse_headers)).json()
    params = {p["code"]: p for p in detail["parameters"]}

    assert [p["display_order"] for p in detail["parameters"]] == sorted(p["display_order"] for p in detail["parameters"])
    assert "redness" not in params
    assert (params["drainage"]["collect_from_day"], params["drainage"]["score_from_day"]) == (0, 5)
    assert (params["spo2"]["collect_to_day"], params["spo2"]["score_to_day"]) == (42, 14)
    assert params["breathless"]["is_emergency"] is True
    assert params["temp_c"]["scoring_summary"].startswith("37.5–38 → 1, 38–38.5 → 2, ≥38.5 → 3")
    # A measure's derived signals are named in the same line, since they raise alerts of their own.
    assert "fever_returned" in params["temp_c"]["scoring_summary"]
    assert params["temp_c"]["direction"] == "higher_is_worse"
    assert params["knee_bend"]["section"] == "progress"
    assert detail["observation_days"] == 84


async def test_unknown_or_unoffered_ruleset_is_not_found(client, db, nurse_headers):
    assert (await client.get("/api/v1/rulesets/999999", headers=nurse_headers)).status_code == 404

    h = await create_hospital(db, "RS-NONE", offers_tkr=False)
    headers = await login_headers(client, h.email, h.password)
    assert (await client.get("/api/v1/rulesets", headers=headers)).json() == []
    ruleset_id = (await client.get("/api/v1/rulesets", headers=nurse_headers)).json()[0]["ruleset_id"]
    assert (await client.get(f"/api/v1/rulesets/{ruleset_id}", headers=headers)).status_code == 404
