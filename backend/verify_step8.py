import asyncio
import sys
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import app

async def test_endpoints():
    print("Testing API endpoints with seeded database...")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Login
        print("\n1. Testing POST /api/v1/auth/login:")
        login_res = await client.post("/api/v1/auth/login", json={
            "email": "nurse.sarah@stmarys.org",
            "password": "password123"
        })
        print(f"Status: {login_res.status_code}")
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token_data = login_res.json()
        token = token_data["access_token"]
        print(f"User: {token_data['full_name']}, Hospital ID: {token_data['hospital_id']}, Role: {token_data['role']}")
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Risk Queue
        print("\n2. Testing GET /api/v1/dashboard/queue:")
        queue_res = await client.get("/api/v1/dashboard/queue", headers=headers)
        assert queue_res.status_code == 200, f"Queue failed: {queue_res.text}"
        queue_data = queue_res.json()
        alerts = queue_data["items"]
        print(f"Total queue items: {queue_data['total']}")
        for idx, a in enumerate(alerts, 1):
            ack_info = f"[ACK by {a['acknowledged_by_name']}]" if a['acknowledged'] else "[UNACKNOWLEDGED]"
            reasons_str = ", ".join(r["text"] if isinstance(r, dict) and "text" in r else str(r) for r in a['reasons']) if a['reasons'] else "No specific reasons"
            print(f"  {idx}. [{a['tier'].upper():<9}] {a['patient_name']:<25} | POD {a['day_after_discharge']} | {reasons_str:<35} {ack_info}")

        # 3. KPIs
        print("\n3. Testing GET /api/v1/dashboard/kpis:")
        kpi_res = await client.get("/api/v1/dashboard/kpis", headers=headers)
        assert kpi_res.status_code == 200, f"KPIs failed: {kpi_res.text}"
        kpis = kpi_res.json()
        print("KPI Results:")
        for k, v in kpis.items():
            print(f"  - {k}: {v}")

        # 4. Acknowledge an unacknowledged alert
        unacked = [a for a in alerts if not a['acknowledged']]
        if unacked:
            target_alert = unacked[0]
            print(f"\n4. Testing POST /api/v1/alerts/{target_alert['alert_id']}/acknowledge:")
            ack_res = await client.post(
                f"/api/v1/alerts/{target_alert['alert_id']}/acknowledge",
                json={"note": "Calling patient immediately to verify symptoms."},
                headers=headers
            )
            print(f"Status: {ack_res.status_code}")
            assert ack_res.status_code == 200, f"Acknowledge failed: {ack_res.text}"
            ack_data = ack_res.json()
            print(f"Acknowledged alert {ack_data['alert_id']} by {ack_data['acknowledged_by_name']} at {ack_data['acknowledged_at']}")

        print("\n[ALL STEP 8 VERIFICATION CHECKS PASSED]")

if __name__ == "__main__":
    asyncio.run(test_endpoints())
