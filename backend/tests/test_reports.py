from datetime import timedelta

from tests.conftest import login_headers
from tests.support import add_check_in, create_alert, create_hospital


async def test_report_counts_alerts_compliance_outcomes_and_adherence(client, db):
    h = await create_hospital(db, "RPT-A")
    headers = await login_headers(client, h.email, h.password)

    # Met the SLA, then resolved; and one never acknowledged, past its window.
    on_time = await create_alert(db, h.episode_id, tier="review", status="acknowledged",
                                 raised_ago=timedelta(hours=2), acknowledged_after=timedelta(minutes=5),
                                 acknowledged_by=h.admin_user_id)
    await create_alert(db, h.episode_id, tier="missed", raised_ago=timedelta(hours=1))
    await client.post(f"/api/v1/alerts/{on_time}/resolve", json={"outcome": "same_day_review"}, headers=headers)

    # Discharged ten days ago: days 0-10 expected. Day 2 has a superseded
    # duplicate, which must still count as one day.
    for day in (0, 1, 2):
        await add_check_in(db, h.episode_id, day, {"temp_c": 37.0})
    await add_check_in(db, h.episode_id, 2, {"temp_c": 36.9}, superseded=True)

    report = (await client.get("/api/v1/reports?days=30", headers=headers)).json()

    summary = report["summary"]
    assert summary["alerts_raised"] == 2
    assert summary["escalated"] == 0
    assert summary["median_ack_secs"] == 300
    assert summary["ack_compliance_pct"] == 50.0
    assert summary["adherence_pct"] == round(3 * 100 / 11, 1)

    totals = {tier: sum(w["counts"][tier] for w in report["alerts_by_week"]) for tier in ("emergency", "critical", "review", "missed")}
    assert totals == {"emergency": 0, "critical": 0, "review": 1, "missed": 1}
    assert report["outcomes"] == {"reassured": 0, "plan_adjusted": 0, "same_day_review": 1, "emergency": 0}

    assert len(report["adherence_by_day"]) == 30
    counted = [d for d in report["adherence_by_day"] if d["expected"]]
    assert len(counted) == 11
    assert sum(d["submitted"] for d in counted) == 3


async def test_quiet_weeks_are_listed_as_zero(client, db):
    h = await create_hospital(db, "RPT-QUIET")
    headers = await login_headers(client, h.email, h.password)
    report = (await client.get("/api/v1/reports?days=60", headers=headers)).json()
    assert len(report["alerts_by_week"]) >= 8
    assert all(sum(w["counts"].values()) == 0 for w in report["alerts_by_week"])
    assert all(w["pct"] is None for w in report["ack_by_week"])
    assert report["summary"]["ack_compliance_pct"] is None
    assert report["summary"]["median_ack_secs"] is None


async def test_report_is_limited_to_the_callers_hospital(client, db, nurse_headers):
    h = await create_hospital(db, "RPT-ISO")
    headers = await login_headers(client, h.email, h.password)
    fixture = (await client.get("/api/v1/reports?days=30", headers=nurse_headers)).json()
    isolated = (await client.get("/api/v1/reports?days=30", headers=headers)).json()
    assert fixture["summary"]["alerts_raised"] >= 6
    assert isolated["summary"]["alerts_raised"] == 0


async def test_report_period_is_bounded(client, nurse_headers):
    for days in (3, 400):
        assert (await client.get(f"/api/v1/reports?days={days}", headers=nurse_headers)).status_code == 422
