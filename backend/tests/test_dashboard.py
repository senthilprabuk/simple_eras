import pytest
import httpx
from typing import Dict

TIER_ORDER = {
    "emergency": 0,
    "critical": 1,
    "review": 2,
    "missed": 3
}

@pytest.mark.asyncio
async def test_queue_sorting_and_schema(client: httpx.AsyncClient, nurse_headers: Dict[str, str]):
    response = await client.get("/api/v1/dashboard/queue", headers=nurse_headers)
    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    assert "total" in data
    items = data["items"]
    assert len(items) == data["total"]
    assert len(items) >= 1

    # Verify strict clinical severity order: emergency -> critical -> review -> missed
    for i in range(len(items) - 1):
        curr_tier = items[i]["tier"]
        next_tier = items[i + 1]["tier"]
        assert TIER_ORDER[curr_tier] <= TIER_ORDER[next_tier], (
            f"Queue out of order at index {i}: {curr_tier} before {next_tier}"
        )

    # Verify schema fields and exclusion of raw numeric evaluation scores
    first = items[0]
    assert "alert_id" in first
    assert "patient_id" in first
    assert "patient_name" in first
    assert "episode_id" in first
    assert "hospital_id" in first
    assert "tier" in first
    assert "reasons" in first
    assert "raised_at" in first
    assert "age_secs" in first
    assert "acknowledged" in first

    # Ensure no raw score leak at top level
    assert "score" not in first
    assert "total_score" not in first
    assert "evaluation_score" not in first

@pytest.mark.asyncio
async def test_queue_multi_tenant_isolation(client: httpx.AsyncClient, h2_headers: Dict[str, str]):
    """Hospital 2 admin must see 0 queue items from Hospital 1."""
    response = await client.get("/api/v1/dashboard/queue", headers=h2_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0

@pytest.mark.asyncio
async def test_kpis_endpoint(client: httpx.AsyncClient, nurse_headers: Dict[str, str]):
    response = await client.get("/api/v1/dashboard/kpis", headers=nurse_headers)
    assert response.status_code == 200
    data = response.json()

    assert "active_patients" in data
    assert "open_alerts" in data
    assert "ack_rate_15min" in data
    assert "missed_checkins_today" in data
    assert "window_days" in data

    assert data["active_patients"] >= 13
    assert data["open_alerts"] >= 1
    assert data["window_days"] == 7
    assert isinstance(data["ack_rate_15min"], (int, float))

@pytest.mark.asyncio
async def test_kpis_custom_window_days(client: httpx.AsyncClient, nurse_headers: Dict[str, str]):
    response = await client.get("/api/v1/dashboard/kpis?window_days=14", headers=nurse_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["window_days"] == 14

@pytest.mark.asyncio
async def test_kpis_invalid_window_days(client: httpx.AsyncClient, nurse_headers: Dict[str, str]):
    # window_days must be between 1 and 90
    response = await client.get("/api/v1/dashboard/kpis?window_days=999", headers=nurse_headers)
    assert response.status_code == 422
