from tests.support import create_alert, episode_for_mrn


async def _alerts(client, headers, query=""):
    res = await client.get(f"/api/v1/alerts?days=365{query}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def test_history_lists_every_state_newest_first(client, nurse_headers):
    data = await _alerts(client, nurse_headers)
    assert data["total"] >= 6
    raised = [i["raised_at"] for i in data["items"]]
    assert raised == sorted(raised, reverse=True)
    for reason in data["items"][0]["reasons"]:
        assert set(reason) == {"name", "detail"}


async def test_filters_by_status_tier_and_patient(client, db, nurse_headers):
    acknowledged = await _alerts(client, nurse_headers, "&status=acknowledged")
    assert acknowledged["items"] and {i["status"] for i in acknowledged["items"]} == {"acknowledged"}

    missed = await _alerts(client, nurse_headers, "&tier=missed")
    assert {i["tier"] for i in missed["items"]} == {"missed"}

    dropout = await _alerts(client, nurse_headers, f"&episode_id={await episode_for_mrn(db, 'FX-06')}")
    assert [(i["patient_name"], i["tier"]) for i in dropout["items"]] == [("Suresh Babu [Drop Out]", "missed")]


async def test_history_records_how_quickly_an_alert_was_acknowledged(client, db, nurse_headers):
    fever = await _alerts(client, nurse_headers, f"&episode_id={await episode_for_mrn(db, 'FX-08')}")
    item = fever["items"][0]
    assert item["acknowledged_by_name"] == "Dr. K. Mehta"
    assert 16 * 60 <= item["ack_secs"] <= 18 * 60
    assert item["ack_window_secs"] == 900


async def test_resolved_alerts_show_outcome_and_resolver(client, db, nurse_headers):
    alert_id = await create_alert(db, await episode_for_mrn(db, "FX-01"), tier="review")
    await client.post(f"/api/v1/alerts/{alert_id}/resolve",
                      json={"outcome": "same_day_review", "note": "Seen in clinic"}, headers=nurse_headers)

    resolved = await _alerts(client, nurse_headers, "&status=resolved")
    item = next(i for i in resolved["items"] if i["alert_id"] == str(alert_id))
    assert item["outcome"] == "same_day_review"
    assert item["outcome_note"] == "Seen in clinic"
    assert item["resolved_by_name"] == "Nurse Sarah Jenkins"


async def test_history_is_limited_to_the_callers_hospital(client, h2_headers):
    assert (await _alerts(client, h2_headers))["total"] == 0


async def test_rejects_unknown_filters(client, nurse_headers):
    for query in ("&status=dismissed", "&tier=urgent", "&days=0"):
        res = await client.get(f"/api/v1/alerts?{query.lstrip('&')}", headers=nurse_headers)
        assert res.status_code == 422, query
