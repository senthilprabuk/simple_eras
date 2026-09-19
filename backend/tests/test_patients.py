from uuid import uuid4

from tests.support import episode_for_mrn


def _trend(timeline, code):
    return next(t for t in timeline["trends"] if t["code"] == code)


def _row(timeline, day):
    return next(r for r in timeline["observations"] if r["day"] == day)


async def _timeline(client, headers, episode_id):
    res = await client.get(f"/api/v1/patients/{episode_id}/timeline", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def test_list_shows_active_patients_most_urgent_first(client, nurse_headers):
    data = (await client.get("/api/v1/patients", headers=nurse_headers)).json()
    assert data["total"] == 12
    assert data["items"][0]["top_open_tier"] == "emergency"
    assert {i["status"] for i in data["items"]} == {"active"}


async def test_list_reports_adherence_from_check_in_days(client, nurse_headers):
    items = (await client.get("/api/v1/patients?search=FX-06", headers=nurse_headers)).json()["items"]
    dropout = items[0]
    assert dropout["patient_name"] == "Suresh Babu [Drop Out]"
    assert dropout["post_op_day"] == 21
    assert dropout["check_in_days"] == 6          # days 0-5, then it stops
    assert dropout["expected_check_in_days"] == 22
    assert dropout["adherence_pct"] == 27.3
    assert dropout["last_check_in_day"] == 5


async def test_search_matches_name_or_mrn_and_treats_wildcards_literally(client, nurse_headers):
    by_name = (await client.get("/api/v1/patients?search=sudden%20clot", headers=nurse_headers)).json()
    assert [i["mrn"] for i in by_name["items"]] == ["FX-03"]

    by_mrn = (await client.get("/api/v1/patients?search=FX-0", headers=nurse_headers)).json()
    assert by_mrn["total"] == 9

    wildcard = (await client.get("/api/v1/patients?search=%25", headers=nurse_headers)).json()
    assert wildcard["total"] == 0


async def test_list_is_limited_to_the_callers_hospital(client, h2_headers):
    data = (await client.get("/api/v1/patients?status=all", headers=h2_headers)).json()
    assert data["total"] == 1
    assert data["items"][0]["patient_name"] == "Patient TEST-02"


async def test_timeline_temperature_trend_carries_the_fever_threshold(client, db, nurse_headers):
    timeline = await _timeline(client, nurse_headers, await episode_for_mrn(db, "FX-02"))
    temp = _trend(timeline, "temp_c")
    assert temp["threshold_direction"] == "above"
    assert temp["baseline"] == 36.8
    assert len(temp["points"]) == 22
    assert {p["threshold"] for p in temp["points"]} == {37.5}
    # The slow-burn infection climbs past the threshold in its second week.
    assert temp["points"][21]["value"] > 38.5
    assert temp["points"][3]["value"] < 37.5


async def test_timeline_pain_threshold_follows_the_day_bands(client, db, nurse_headers):
    pain = _trend(await _timeline(client, nurse_headers, await episode_for_mrn(db, "FX-02")), "pain")
    assert pain["points"][2]["threshold"] == 8
    assert pain["points"][5]["threshold"] == 4
    assert pain["points"][15]["threshold"] == 3


async def test_timeline_steps_threshold_tracks_half_the_personal_best(client, db, nurse_headers):
    steps = _trend(await _timeline(client, nurse_headers, await episode_for_mrn(db, "FX-12")), "steps")
    assert steps["threshold_direction"] == "below"
    best_before_drop = max(p["value"] for p in steps["points"][:12])
    assert steps["points"][12]["threshold"] == round(best_before_drop / 2, 2)
    assert steps["points"][12]["value"] < steps["points"][12]["threshold"]


async def test_days_without_a_check_in_stay_as_gaps(client, db, nurse_headers):
    timeline = await _timeline(client, nurse_headers, await episode_for_mrn(db, "FX-05"))
    for day in (2, 3, 6, 9, 10):
        assert _row(timeline, day)["checked_in"] is False
        assert _trend(timeline, "temp_c")["points"][day]["value"] is None
    assert _row(timeline, 1)["checked_in"] is True


async def test_observations_show_red_flags_by_day(client, db, nurse_headers):
    clot = await _timeline(client, nurse_headers, await episode_for_mrn(db, "FX-03"))
    assert [c["code"] for c in clot["observation_columns"]] == ["breathless", "calf_pain", "drainage", "chills"]
    assert _row(clot, 3)["values"]["calf_pain"] == {"value": False, "asked": True}
    assert _row(clot, 4)["values"]["calf_pain"] == {"value": True, "asked": True}

    pe = await _timeline(client, nurse_headers, await episode_for_mrn(db, "FX-04"))
    assert [r["day"] for r in pe["observations"] if r["values"]["breathless"]["value"]] == [6, 7, 8]
    assert next(c for c in pe["observation_columns"] if c["code"] == "breathless")["is_emergency"] is True


async def test_observations_after_the_patient_stops_checking_in(client, db, nurse_headers):
    dropout = await _timeline(client, nurse_headers, await episode_for_mrn(db, "FX-06"))
    assert all(not _row(dropout, d)["checked_in"] for d in range(6, 22))
    assert _row(dropout, 10)["values"]["chills"] == {"value": None, "asked": True}


async def test_timeline_of_another_hospitals_patient_is_not_found(client, db, h2_headers):
    res = await client.get(f"/api/v1/patients/{await episode_for_mrn(db, 'FX-01')}/timeline", headers=h2_headers)
    assert res.status_code == 404


async def test_timeline_of_unknown_episode_is_not_found(client, nurse_headers):
    assert (await client.get(f"/api/v1/patients/{uuid4()}/timeline", headers=nurse_headers)).status_code == 404
