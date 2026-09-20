import asyncio
from datetime import timedelta
from typing import Dict
from uuid import uuid4

import httpx
from sqlalchemy import text

from tests.support import admin_id_for, create_alert, episode_for_mrn


async def _alert_row(db, alert_id):
    return (await db.execute(text("""
        SELECT status, outcome, outcome_note, acknowledged_at, acknowledged_by, resolved_at, resolved_by
        FROM txn.alert WHERE alert_id = :a
    """), {"a": alert_id})).mappings().one()


async def test_acknowledge_alert_lifecycle(client: httpx.AsyncClient, nurse_headers, h2_headers):
    items = (await client.get("/api/v1/dashboard/queue", headers=nurse_headers)).json()["items"]
    unacked = [a for a in items if not a["acknowledged"]]
    assert unacked, "seed data should include an unacknowledged alert"
    alert_id = unacked[0]["alert_id"]

    # Another hospital gets 404, never 403, so it cannot learn the alert exists.
    res = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=h2_headers)
    assert res.status_code == 404
    assert res.json()["detail"] == "Alert not found"

    res = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=nurse_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["alert_id"] == alert_id
    assert data["status"] == "acknowledged"
    assert data["acknowledged_by_name"] == "Nurse Sarah Jenkins"

    res = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=nurse_headers)
    assert res.status_code == 409
    assert "acknowledged" in res.json()["detail"].lower()


async def test_acknowledge_nonexistent_alert(client: httpx.AsyncClient, nurse_headers):
    res = await client.post(f"/api/v1/alerts/{uuid4()}/acknowledge", headers=nurse_headers)
    assert res.status_code == 404
    assert res.json()["detail"] == "Alert not found"


async def test_simultaneous_acknowledgements_exactly_one_wins(client, db, nurse_headers, surgeon_headers):
    alert_id = await create_alert(db, await episode_for_mrn(db, "FX-01"))

    results = await asyncio.gather(
        client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=nurse_headers),
        client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=surgeon_headers),
    )
    assert sorted(r.status_code for r in results) == [200, 409]

    # The stored acknowledger is the one who was told they succeeded.
    winner = next(r for r in results if r.status_code == 200).json()
    assert str((await _alert_row(db, alert_id))["acknowledged_by"]) == winner["acknowledged_by"]


async def test_expired_alert_cannot_be_acknowledged(client, db, nurse_headers):
    alert_id = await create_alert(db, await episode_for_mrn(db, "FX-01"), status="expired")
    res = await client.post(f"/api/v1/alerts/{alert_id}/acknowledge", headers=nurse_headers)
    assert res.status_code == 409
    assert "expired" in res.json()["detail"]


async def test_resolve_records_outcome_note_and_resolver(client, db, nurse_headers, surgeon_headers):
    nurse_id = await admin_id_for(db, "nurse.sarah@stmarys.org")
    surgeon_id = await admin_id_for(db, "dr.mehta@stmarys.org")
    alert_id = await create_alert(
        db, await episode_for_mrn(db, "FX-01"), status="acknowledged",
        raised_ago=timedelta(minutes=10), acknowledged_after=timedelta(minutes=2), acknowledged_by=nurse_id,
    )

    res = await client.post(
        f"/api/v1/alerts/{alert_id}/resolve",
        json={"outcome": "plan_adjusted", "note": "  Antibiotics started, review in 48h.  "},
        headers=surgeon_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "resolved"
    assert data["outcome"] == "plan_adjusted"
    assert data["outcome_note"] == "Antibiotics started, review in 48h."
    assert data["resolved_by_name"] == "Dr. K. Mehta"

    row = await _alert_row(db, alert_id)
    assert row["status"] == "resolved"
    assert row["outcome"] == "plan_adjusted"
    assert row["resolved_by"] == surgeon_id
    assert row["acknowledged_by"] == nurse_id, "resolving must not overwrite who acknowledged first"

    queue = (await client.get("/api/v1/dashboard/queue?limit=500", headers=nurse_headers)).json()
    assert alert_id not in {str(i["alert_id"]) for i in queue["items"]}


async def test_resolving_an_unacknowledged_alert_also_acknowledges_it(client, db, nurse_headers):
    alert_id = await create_alert(db, await episode_for_mrn(db, "FX-01"))
    res = await client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"outcome": "reassured"}, headers=nurse_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["outcome_note"] is None
    assert data["acknowledged_at"] == data["resolved_at"]
    assert (await _alert_row(db, alert_id))["acknowledged_by"] is not None


async def test_resolving_twice_conflicts(client, db, nurse_headers):
    alert_id = await create_alert(db, await episode_for_mrn(db, "FX-01"))
    first = await client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"outcome": "reassured"}, headers=nurse_headers)
    assert first.status_code == 200
    second = await client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"outcome": "emergency"}, headers=nurse_headers)
    assert second.status_code == 409
    assert "resolved" in second.json()["detail"]
    assert (await _alert_row(db, alert_id))["outcome"] == "reassured"


async def test_resolve_requires_a_known_outcome(client, db, nurse_headers: Dict[str, str]):
    alert_id = await create_alert(db, await episode_for_mrn(db, "FX-01"))
    for body in ({}, {"outcome": "dismissed"}, {"outcome": "reassured", "note": "x" * 2001}):
        res = await client.post(f"/api/v1/alerts/{alert_id}/resolve", json=body, headers=nurse_headers)
        assert res.status_code == 422, body
    assert (await _alert_row(db, alert_id))["status"] == "open"


async def test_resolve_across_hospitals_is_not_found(client, db, h2_headers):
    alert_id = await create_alert(db, await episode_for_mrn(db, "FX-01"))
    res = await client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"outcome": "reassured"}, headers=h2_headers)
    assert res.status_code == 404
    assert (await _alert_row(db, alert_id))["status"] == "open"


async def test_history_carries_the_operative_side_and_a_number_to_call(client, db, nurse_headers):
    """
    Two facts a nurse needs before acting, on the row rather than a click away.

    Calf pain reads differently depending on which leg it is, and an emergency
    is answered by phoning the patient, so both belong beside the alert. The
    side is nullable for episodes enrolled before it was recorded, which the
    screen shows as "side not recorded" rather than guessing.
    """
    episode_id = await episode_for_mrn(db, "FX-03")
    await create_alert(db, episode_id, tier="critical")

    items = (await client.get("/api/v1/alerts", headers=nurse_headers)).json()["items"]
    row = next(a for a in items if a["mrn"] == "FX-03")

    assert row["operative_side"] == "right"
    assert row["procedure_code"] == "TKR"
    assert row["phone_e164"].startswith("+91")

    # The fixture database is built once for the whole session, so anything this
    # test changes it must change back: a patient left without a side here fails
    # an assertion in another file that has no idea this test exists.
    try:
        await db.execute(text("UPDATE txn.patient_episode SET operative_side = NULL WHERE episode_id = :e"),
                         {"e": episode_id})
        await db.commit()

        items = (await client.get("/api/v1/alerts", headers=nurse_headers)).json()["items"]
        assert next(a for a in items if a["mrn"] == "FX-03")["operative_side"] is None
    finally:
        await db.execute(text("UPDATE txn.patient_episode SET operative_side = :s WHERE episode_id = :e"),
                         {"s": row["operative_side"], "e": episode_id})
        await db.commit()
