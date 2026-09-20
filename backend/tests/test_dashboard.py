from datetime import datetime, timedelta
from typing import Dict

import httpx
from sqlalchemy import text

from tests.conftest import login_headers
from tests.support import create_alert, create_hospital

TIER_ORDER = {"emergency": 0, "critical": 1, "review": 2, "missed": 3}


async def test_queue_is_ordered_by_tier_then_age(client: httpx.AsyncClient, nurse_headers: Dict[str, str]):
    res = await client.get("/api/v1/dashboard/queue", headers=nurse_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) >= 1

    keys = [(TIER_ORDER[i["tier"]], datetime.fromisoformat(i["raised_at"])) for i in items]
    assert keys == sorted(keys), "queue must be most severe first, then oldest first"


async def test_queue_rows_carry_sla_and_no_scores(client: httpx.AsyncClient, nurse_headers: Dict[str, str]):
    first = (await client.get("/api/v1/dashboard/queue", headers=nurse_headers)).json()["items"][0]
    assert first["ack_window_secs"] == 900
    for field in ("alert_id", "patient_name", "episode_id", "tier", "reasons", "raised_at", "age_secs"):
        assert field in first
    for leaked in ("score", "total_score"):
        assert leaked not in first
    # Seeded reasons store score and weight; the API must not pass them through.
    for reason in first["reasons"]:
        assert set(reason) == {"name", "detail"}


async def test_queue_pages_are_stable_and_complete(client: httpx.AsyncClient, nurse_headers: Dict[str, str]):
    whole = (await client.get("/api/v1/dashboard/queue?limit=500", headers=nurse_headers)).json()
    ids = [i["alert_id"] for i in whole["items"]]
    assert whole["total"] == len(ids)

    paged = []
    for offset in range(0, len(ids), 2):
        page = (await client.get(f"/api/v1/dashboard/queue?limit=2&offset={offset}", headers=nurse_headers)).json()
        assert page["total"] == whole["total"]
        paged += [i["alert_id"] for i in page["items"]]
    assert paged == ids


async def test_queue_multi_tenant_isolation(client: httpx.AsyncClient, h2_headers: Dict[str, str]):
    data = (await client.get("/api/v1/dashboard/queue", headers=h2_headers)).json()
    assert data["total"] == 0
    assert data["items"] == []


async def test_kpis_census(client: httpx.AsyncClient, nurse_headers: Dict[str, str]):
    data = (await client.get("/api/v1/dashboard/kpis", headers=nurse_headers)).json()
    assert data["active_patients"] == 14
    assert data["ack_window_secs"] == 900
    assert data["window_days"] == 7
    assert data["unresolved_alerts"] >= data["unacknowledged_alerts"] >= 1
    assert data["patients_with_open_alerts"] <= data["active_patients"]


async def test_ack_compliance_counts_breaches_and_ignores_undecided(client, db):
    h = await create_hospital(db, "KPI-A")
    ep = h.episode_id
    await create_alert(db, ep, tier="review", status="acknowledged",
                       raised_ago=timedelta(hours=2), acknowledged_after=timedelta(minutes=5))   # met
    await create_alert(db, ep, tier="review", status="acknowledged",
                       raised_ago=timedelta(hours=2), acknowledged_after=timedelta(minutes=20))  # breach
    await create_alert(db, ep, tier="review", raised_ago=timedelta(minutes=30))                  # breach, never acked
    await create_alert(db, ep, tier="review", raised_ago=timedelta(minutes=2))                   # still in window

    data = (await client.get("/api/v1/dashboard/kpis", headers=await login_headers(client, h.email, h.password))).json()
    assert data["ack_decided_alerts"] == 3
    assert data["ack_compliance_pct"] == 33.3
    assert data["unresolved_alerts"] == 4
    assert data["unacknowledged_alerts"] == 2
    assert data["active_patients"] == 1
    assert data["patients_with_open_alerts"] == 1


async def test_zero_compliance_is_reported_as_zero_not_perfect(client, db):
    h = await create_hospital(db, "KPI-ZERO")
    await create_alert(db, h.episode_id, tier="review", status="acknowledged",
                       raised_ago=timedelta(hours=1), acknowledged_after=timedelta(minutes=40))
    data = (await client.get("/api/v1/dashboard/kpis", headers=await login_headers(client, h.email, h.password))).json()
    assert data["ack_compliance_pct"] == 0.0


async def test_no_verdict_yet_is_null_rather_than_100(client, db):
    h = await create_hospital(db, "KPI-NONE")
    await create_alert(db, h.episode_id, tier="review", raised_ago=timedelta(minutes=1))
    data = (await client.get("/api/v1/dashboard/kpis", headers=await login_headers(client, h.email, h.password))).json()
    assert data["ack_compliance_pct"] is None
    assert data["ack_decided_alerts"] == 0


async def test_ack_compliance_uses_the_hospitals_own_window(client, db):
    h = await create_hospital(db, "KPI-HOUR", ack_window_secs=3600)
    await create_alert(db, h.episode_id, tier="review", status="acknowledged",
                       raised_ago=timedelta(hours=2), acknowledged_after=timedelta(minutes=20))
    data = (await client.get("/api/v1/dashboard/kpis", headers=await login_headers(client, h.email, h.password))).json()
    assert data["ack_window_secs"] == 3600
    assert data["ack_compliance_pct"] == 100.0


async def test_missed_checkins_today_uses_the_hospitals_timezone(client, db):
    # UTC+14: local midnight is ten hours before UTC midnight, so a UTC calendar
    # day and the hospital's calendar day disagree for most of every day.
    h = await create_hospital(db, "KPI-TZ", timezone_name="Pacific/Kiritimati")
    for offset in ("+ interval '1 minute'", "- interval '1 minute'"):
        await db.execute(text(f"""
            INSERT INTO txn.check_in_evaluation
                (episode_id, ruleset_id, day_after_discharge, tier, reasons, reason_key, evaluated_at)
            SELECT e.episode_id, e.ruleset_id, 9, 'missed', '[]'::jsonb, 'missed',
                   (date_trunc('day', now() AT TIME ZONE 'Pacific/Kiritimati') AT TIME ZONE 'Pacific/Kiritimati') {offset}
            FROM txn.patient_episode e WHERE e.episode_id = :ep
        """), {"ep": h.episode_id})
    await db.commit()

    data = (await client.get("/api/v1/dashboard/kpis", headers=await login_headers(client, h.email, h.password))).json()
    assert data["missed_checkins_today"] == 1


async def test_kpis_custom_window_days(client: httpx.AsyncClient, nurse_headers: Dict[str, str]):
    res = await client.get("/api/v1/dashboard/kpis?window_days=14", headers=nurse_headers)
    assert res.status_code == 200
    assert res.json()["window_days"] == 14


async def test_kpis_invalid_window_days(client: httpx.AsyncClient, nurse_headers: Dict[str, str]):
    res = await client.get("/api/v1/dashboard/kpis?window_days=999", headers=nurse_headers)
    assert res.status_code == 422
