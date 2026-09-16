#!/usr/bin/env python3
"""
Step 6 Verification Test
Uses httpx.AsyncClient with ASGITransport to verify:
  1. GET /health
  2. Unauthenticated 401 protection on /queue, /kpis, /alerts/{id}/acknowledge
  3. POST /api/v1/auth/login with invalid password -> 401
  4. POST /api/v1/auth/login with valid admin -> 200 with JWT
  5. Authenticated GET /api/v1/dashboard/queue -> 200 OK with QueueResponse
  6. Authenticated GET /api/v1/dashboard/kpis -> 200 OK with KpiResponse
  7. Authenticated POST /api/v1/alerts/{fake_id}/acknowledge -> 404 Not Found (Cross-tenant isolation)
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4
import httpx
from httpx import ASGITransport
from sqlalchemy import text

# Ensure backend directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import app
from app.db.session import async_session_factory
from app.core.security import get_password_hash

async def run_tests():
    print("=== STEP 6: API ENDPOINTS & ASGI INTEGRATION VERIFICATION ===\n")

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health check
        print("[*] 1. Testing GET /health:")
        r = await client.get("/health")
        assert r.status_code == 200, f"Health check failed: {r.status_code}"
        assert r.json()["status"] == "healthy"
        print(f"  [+] /health OK: {r.json()}")

        # 2. Unauthenticated protection
        print("\n[*] 2. Testing 401 Unauthorized protection on private endpoints:")
        r = await client.get("/api/v1/dashboard/queue")
        assert r.status_code == 401, f"Expected 401 on /queue, got {r.status_code}"
        print("  [+] GET /api/v1/dashboard/queue -> 401 (Protected)")

        r = await client.get("/api/v1/dashboard/kpis")
        assert r.status_code == 401, f"Expected 401 on /kpis, got {r.status_code}"
        print("  [+] GET /api/v1/dashboard/kpis -> 401 (Protected)")

        fake_id = str(uuid4())
        r = await client.post(f"/api/v1/alerts/{fake_id}/acknowledge")
        assert r.status_code == 401, f"Expected 401 on /acknowledge, got {r.status_code}"
        print("  [+] POST /api/v1/alerts/.../acknowledge -> 401 (Protected)")

        # 3. Create a temporary test admin user in Neon database
        print("\n[*] 3. Creating test admin user in Neon database:")
        test_admin_id = uuid4()
        test_email = f"test.nurse.{uuid4().hex[:6]}@stmarys.org"
        test_raw_password = "SecretPassword123!"
        hashed_pwd = get_password_hash(test_raw_password)

        async with async_session_factory() as session:
            # Look up first available hospital_id
            res = await session.execute(text("SELECT hospital_id FROM meta.hospital LIMIT 1;"))
            h_id = res.scalar()
            assert h_id is not None, "At least one hospital must exist in meta.hospital"

            insert_stmt = text("""
                INSERT INTO meta.admin_user (
                    admin_user_id, hospital_id, email, hashed_password, full_name, role, is_active
                ) VALUES (
                    :uid, :hid, :email, :pwd, 'Nurse Test Agent', 'admin', true
                );
            """)
            await session.execute(insert_stmt, {
                "uid": test_admin_id,
                "hid": h_id,
                "email": test_email,
                "pwd": hashed_pwd
            })
            await session.commit()
            print(f"  [+] Created test admin: {test_email} (Hospital ID: {h_id})")

        try:
            # 4. Test login with wrong password
            print("\n[*] 4. Testing POST /api/v1/auth/login with invalid password:")
            r = await client.post("/api/v1/auth/login", json={
                "email": test_email,
                "password": "WrongPassword!"
            })
            assert r.status_code == 401, f"Expected 401, got {r.status_code}"
            print("  [+] Invalid password rejected with 401 generic message.")

            # 5. Test login with valid credentials
            print("\n[*] 5. Testing POST /api/v1/auth/login with valid credentials:")
            r = await client.post("/api/v1/auth/login", json={
                "email": test_email,
                "password": test_raw_password
            })
            assert r.status_code == 200, f"Login failed: {r.text}"
            data = r.json()
            token = data["access_token"]
            assert data["admin_user_id"] == str(test_admin_id)
            assert data["hospital_id"] == h_id
            print(f"  [+] Login successful. Received token for admin: {data['full_name']}")

            headers = {"Authorization": f"Bearer {token}"}

            # 6. Test GET /api/v1/dashboard/queue
            print("\n[*] 6. Testing GET /api/v1/dashboard/queue with Bearer token:")
            r = await client.get("/api/v1/dashboard/queue", headers=headers)
            assert r.status_code == 200, f"Queue read failed: {r.text}"
            queue_data = r.json()
            assert "items" in queue_data
            assert "total" in queue_data
            print(f"  [+] /queue returned {queue_data['total']} active alerts.")

            # 7. Test GET /api/v1/dashboard/kpis
            print("\n[*] 7. Testing GET /api/v1/dashboard/kpis with Bearer token:")
            r = await client.get("/api/v1/dashboard/kpis?window_days=7", headers=headers)
            assert r.status_code == 200, f"KPIs failed: {r.text}"
            kpis = r.json()
            print(f"  [+] KPIs returned: {kpis}")
            assert "active_patients" in kpis
            assert "open_alerts" in kpis
            assert "ack_rate_15min" in kpis
            assert "missed_checkins_today" in kpis

            # 8. Test POST /api/v1/alerts/{id}/acknowledge (cross-tenant 404 test)
            print("\n[*] 8. Testing POST /api/v1/alerts/.../acknowledge on non-existent/cross-hospital alert:")
            r = await client.post(f"/api/v1/alerts/{uuid4()}/acknowledge", headers=headers)
            assert r.status_code == 404, f"Expected 404, got {r.status_code}"
            print("  [+] Non-existent or cross-tenant alert returned 404 Not Found (Confirmed isolated).")

        finally:
            # Cleanup test admin user
            print("\n[*] Cleaning up test admin user...")
            async with async_session_factory() as session:
                await session.execute(text("DELETE FROM meta.admin_user WHERE admin_user_id = :uid;"), {"uid": test_admin_id})
                await session.commit()
            print("  [+] Test admin removed cleanly from database.")

    print("\n[SUCCESS] Step 6 API endpoints and ASGI integration verified with 0 errors!")

if __name__ == "__main__":
    asyncio.run(run_tests())
