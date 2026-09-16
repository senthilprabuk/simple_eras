import asyncio
import sys
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import app

async def test_frontend_integration():
    print("=== STEP 10: NEXT.JS FRONTEND INTEGRATION VERIFICATION ===\n")
    
    frontend_origin = "http://localhost:3000"
    
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        # 1. CORS Preflight Check
        print("[*] 1. Testing CORS Preflight (OPTIONS /api/v1/dashboard/queue):")
        preflight_res = await client.options(
            "/api/v1/dashboard/queue",
            headers={
                "Origin": frontend_origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            }
        )
        print(f"  Status: {preflight_res.status_code}")
        allow_origin = preflight_res.headers.get("access-control-allow-origin")
        print(f"  Access-Control-Allow-Origin: {allow_origin}")
        assert allow_origin in [frontend_origin, "*"], f"CORS origin not allowed: {allow_origin}"
        print("  [+] CORS Preflight PASSED")

        # 2. Login from Frontend Origin
        print("\n[*] 2. Testing Login from Frontend Origin:")
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "nurse.sarah@stmarys.org", "password": "password123"},
            headers={"Origin": frontend_origin}
        )
        assert login_res.status_code == 200
        token_data = login_res.json()
        token = token_data["access_token"]
        assert login_res.headers.get("access-control-allow-origin") in [frontend_origin, "*"]
        print(f"  [+] Logged in: {token_data['full_name']} (Role: {token_data['role']})")

        # 3. Queue Fetch with CORS
        print("\n[*] 3. Testing Queue Fetch from Frontend Origin:")
        queue_res = await client.get(
            "/api/v1/dashboard/queue",
            headers={
                "Origin": frontend_origin,
                "Authorization": f"Bearer {token}"
            }
        )
        assert queue_res.status_code == 200
        queue_data = queue_res.json()
        print(f"  [+] Retrieved {queue_data['total']} prioritized alert items from Neon PostgreSQL.")
        assert len(queue_data["items"]) == queue_data["total"]

        # 4. KPIs Fetch with CORS
        print("\n[*] 4. Testing KPIs Fetch from Frontend Origin:")
        kpi_res = await client.get(
            "/api/v1/dashboard/kpis",
            headers={
                "Origin": frontend_origin,
                "Authorization": f"Bearer {token}"
            }
        )
        assert kpi_res.status_code == 200
        kpis = kpi_res.json()
        print(f"  [+] Active Patients: {kpis['active_patients']}")
        print(f"  [+] Open Alerts: {kpis['open_alerts']}")
        print(f"  [+] 15m SLA Ack Rate: {kpis['ack_rate_15min']}%")
        print(f"  [+] Missed Check-ins Today: {kpis['missed_checkins_today']}")

        print("\n==========================================================")
        print(" [ALL STEP 10 FRONTEND INTEGRATION CHECKS PASSED]        ")
        print("==========================================================")

if __name__ == "__main__":
    asyncio.run(test_frontend_integration())
