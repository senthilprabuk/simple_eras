import pytest
import httpx
from typing import Dict
from uuid import uuid4

@pytest.mark.asyncio
async def test_acknowledge_alert_lifecycle(
    client: httpx.AsyncClient,
    nurse_headers: Dict[str, str],
    h2_headers: Dict[str, str]
):
    # 1. Find an unacknowledged alert from Hospital 1
    queue_res = await client.get("/api/v1/dashboard/queue", headers=nurse_headers)
    assert queue_res.status_code == 200
    items = queue_res.json()["items"]
    unacked = [a for a in items if not a["acknowledged"]]
    assert len(unacked) > 0, "Expected at least one unacknowledged alert from seed data"

    target_alert = unacked[0]
    alert_id = target_alert["alert_id"]

    # 2. Test cross-hospital isolation: Hospital 2 admin attempts to acknowledge Hospital 1 alert
    h2_ack_res = await client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge",
        json={"note": "Malicious or accidental cross-hospital attempt"},
        headers=h2_headers
    )
    # Must return 404 Not Found to prevent leaking whether the alert exists
    assert h2_ack_res.status_code == 404
    assert h2_ack_res.json()["detail"] == "Alert not found"

    # 3. Happy Path: Nurse Sarah acknowledges the alert
    ack_res = await client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge",
        json={"note": "Patient called, vitals stable, dressing changed."},
        headers=nurse_headers
    )
    assert ack_res.status_code == 200
    ack_data = ack_res.json()
    assert ack_data["alert_id"] == alert_id
    assert ack_data["status"] == "acknowledged"
    assert ack_data["acknowledged_at"] is not None
    assert ack_data["acknowledged_by_name"] == "Nurse Sarah Jenkins"

    # 4. Conflict: Attempt to acknowledge the exact same alert a second time
    conflict_res = await client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge",
        json={"note": "Trying to acknowledge again"},
        headers=nurse_headers
    )
    assert conflict_res.status_code == 409
    assert "acknowledged" in conflict_res.json()["detail"].lower()

@pytest.mark.asyncio
async def test_acknowledge_nonexistent_alert(
    client: httpx.AsyncClient,
    nurse_headers: Dict[str, str]
):
    fake_alert_id = str(uuid4())
    response = await client.post(
        f"/api/v1/alerts/{fake_alert_id}/acknowledge",
        json={"note": "Fake alert check"},
        headers=nurse_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Alert not found"
