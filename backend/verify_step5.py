#!/usr/bin/env python3
"""
Step 5 Verification Test
Validates:
  1. Auth schemas: LoginRequest email normalization, validation, TokenResponse
  2. Dashboard schemas: QueueRow, QueueResponse, KpiResponse
  3. Alert schemas: AlertAcknowledgeResponse
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Ensure backend directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.schemas import (
    LoginRequest,
    TokenResponse,
    QueueRow,
    QueueResponse,
    KpiResponse,
    AlertAcknowledgeResponse,
)

def test_schemas():
    print("=== STEP 5: PYDANTIC V2 SCHEMAS VERIFICATION ===\n")

    # 1. Test LoginRequest
    print("[*] 1. Testing LoginRequest:")
    req = LoginRequest(email="  Nurse.Sarah@StMarys.org  ", password="SecretPassword123")
    assert req.email == "nurse.sarah@stmarys.org", "Email must be normalized to lowercase and trimmed"
    assert req.hospital_id is None, "hospital_id should default to None"
    print(f"  [+] Email normalization: {req.email}")

    req_with_hospital = LoginRequest(email="nurse@stmarys.org", password="SecretPassword123", hospital_id=101)
    assert req_with_hospital.hospital_id == 101
    print("  [+] Optional hospital_id disambiguation: OK")

    # 2. Test TokenResponse
    print("\n[*] 2. Testing TokenResponse:")
    admin_id = uuid4()
    token_resp = TokenResponse(
        access_token="sample-jwt-token",
        admin_user_id=admin_id,
        hospital_id=1,
        full_name="Nurse Sarah Jenkins",
        role="admin",
    )
    assert token_resp.token_type == "bearer"
    assert token_resp.admin_user_id == admin_id
    print(f"  [+] TokenResponse serialization: {token_resp.model_dump_json()}")

    # 3. Test QueueRow & QueueResponse
    print("\n[*] 3. Testing QueueRow & QueueResponse:")
    sample_alert_id = uuid4()
    sample_patient_id = uuid4()
    sample_episode_id = uuid4()
    now = datetime.now(timezone.utc)

    row = QueueRow(
        alert_id=sample_alert_id,
        patient_id=sample_patient_id,
        patient_name="H. Thorne",
        mrn="ER-9042",
        episode_id=sample_episode_id,
        hospital_id=1,
        hospital_name="St. Mary's Orthopedic Center",
        procedure_code="TKR",
        day_after_discharge=4,
        tier="emergency",
        reasons=[
            {"name": "calf_pain", "score": 3, "weight": 3, "detail": "Calf swelling & acute sharp pain"},
            {"name": "pe_risk", "score": 3, "weight": 0, "detail": "Suspected DVT trigger"}
        ],
        raised_at=now,
        age_secs=180,
        acknowledged=False,
    )
    assert row.tier == "emergency"
    assert len(row.reasons) == 2
    assert row.acknowledged is False
    print(f"  [+] QueueRow parsed: {row.patient_name} - Tier: {row.tier} ({row.age_secs}s ago)")

    queue_resp = QueueResponse(items=[row], total=1)
    assert len(queue_resp.items) == 1
    assert queue_resp.total == 1
    print("  [+] QueueResponse wrapping: OK")

    # 4. Test KpiResponse
    print("\n[*] 4. Testing KpiResponse:")
    kpi = KpiResponse(
        active_patients=142,
        open_alerts=7,
        ack_rate_15min=94.2,
        missed_checkins_today=4,
        window_days=7
    )
    assert kpi.ack_rate_15min == 94.2
    assert kpi.open_alerts == 7
    print(f"  [+] KpiResponse parsed: {kpi.model_dump()}")

    # 5. Test AlertAcknowledgeResponse
    print("\n[*] 5. Testing AlertAcknowledgeResponse:")
    ack = AlertAcknowledgeResponse(
        alert_id=sample_alert_id,
        acknowledged_at=now,
        acknowledged_by=admin_id,
        acknowledged_by_name="Nurse Sarah Jenkins"
    )
    assert ack.status == "acknowledged"
    assert ack.acknowledged_by == admin_id
    print(f"  [+] AlertAcknowledgeResponse parsed: {ack.model_dump()}")

    print("\n[SUCCESS] Step 5 Pydantic v2 schemas verified with 0 errors!")

if __name__ == "__main__":
    test_schemas()
