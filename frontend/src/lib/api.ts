/**
 * ERAS Clinical Remote Monitoring - Backend API Client
 * Connects Next.js Frontend to FastAPI Backend on Port 8000
 */

import { PatientQueueItem } from "@/data/mockPatients";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface QueueRow {
  alert_id: string;
  patient_id: string;
  patient_name: string;
  mrn: string | null;
  episode_id: string;
  hospital_id: number;
  hospital_name: string;
  procedure_code: string;
  day_after_discharge: number;
  tier: "emergency" | "critical" | "review" | "missed";
  reasons: any[];
  raised_at: string;
  age_secs: number;
  acknowledged: boolean;
  acknowledged_at: string | null;
  acknowledged_by_name: string | null;
}

export interface QueueResponse {
  items: QueueRow[];
  total: number;
}

export interface KpiResponse {
  active_patients: number;
  open_alerts: number;
  ack_rate_15min: number;
  missed_checkins_today: number;
  window_days: number;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  admin_user_id: string;
  hospital_id: number;
  full_name: string;
  role: string;
}

let cachedToken: string | null = null;

/**
 * Authenticate with the FastAPI backend using demo nurse credentials.
 */
export async function loginDemoAdmin(): Promise<string> {
  if (cachedToken) {
    return cachedToken;
  }

  const res = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: "nurse.sarah@stmarys.org",
      password: "password123",
    }),
  });

  if (!res.ok) {
    throw new Error(`Authentication failed with status ${res.status}`);
  }

  const data: TokenResponse = await res.json();
  cachedToken = data.access_token;
  return cachedToken;
}

/**
 * Fetch the risk queue for the logged-in hospital.
 */
export async function fetchQueue(): Promise<QueueResponse> {
  const token = await loginDemoAdmin();
  const res = await fetch(`${API_BASE_URL}/api/v1/dashboard/queue`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch queue: ${res.statusText}`);
  }

  return res.json();
}

/**
 * Fetch rolling KPIs for the dashboard header.
 */
export async function fetchKpis(windowDays: number = 7): Promise<KpiResponse> {
  const token = await loginDemoAdmin();
  const res = await fetch(`${API_BASE_URL}/api/v1/dashboard/kpis?window_days=${windowDays}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch KPIs: ${res.statusText}`);
  }

  return res.json();
}

/**
 * Acknowledge an open alert.
 */
export async function acknowledgeAlert(alertId: string, note?: string): Promise<any> {
  const token = await loginDemoAdmin();
  const res = await fetch(`${API_BASE_URL}/api/v1/alerts/${alertId}/acknowledge`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ note: note || "Acknowledged from clinical workstation" }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Acknowledge failed: ${res.status}`);
  }

  return res.json();
}

/**
 * Adapter to translate backend QueueRow to frontend PatientQueueItem.
 */
export function mapQueueRowToPatientItem(row: QueueRow): PatientQueueItem {
  // Age calculation
  const mins = Math.max(1, Math.floor(row.age_secs / 60));
  const alertAgeText = mins < 60 ? `${mins}m ago` : `${Math.floor(mins / 60)}h ago`;

  // SLA calculation (15 min SLA window = 900s)
  const remainingSecs = 900 - row.age_secs;
  const remainingMins = Math.ceil(remainingSecs / 60);
  const slaText =
    row.acknowledged
      ? "SLA Met"
      : remainingMins > 0
      ? `${remainingMins}m SLA remains`
      : "SLA Breached";

  // Reasons transformation
  const formattedReasons = (row.reasons || []).map((r: any) => {
    if (typeof r === "object" && r !== null) {
      const text = r.detail || r.text || r.name || JSON.stringify(r);
      const isSevere = (r.weight && r.weight >= 3) || (r.score && r.score >= 3) || !!r.isSevere;
      return { text, isSevere };
    }
    return { text: String(r), isSevere: false };
  });

  // Action type mapping
  let actionType: "call" | "acknowledge" | "ping" | "none" = "acknowledge";
  if (row.acknowledged) {
    actionType = "none";
  } else if (row.tier === "emergency") {
    actionType = "call";
  } else if (row.tier === "missed") {
    actionType = "ping";
  }

  // Procedure display mapping
  const procedureDisplay =
    row.procedure_code === "TKA_PRIMARY"
      ? "Left TKA"
      : row.procedure_code === "TKA_BILATERAL"
      ? "Bilateral TKA"
      : row.procedure_code || "Knee Arthroplasty";

  return {
    id: row.patient_id,
    name: row.patient_name,
    mrn: row.mrn || "N/A",
    post_op_day: row.day_after_discharge,
    procedure: procedureDisplay,
    tier: row.tier,
    reasons: formattedReasons,
    alert_id: row.alert_id,
    alert_age_text: alertAgeText,
    sla_text: slaText,
    acknowledged: row.acknowledged,
    acknowledged_text: row.acknowledged
      ? row.acknowledged_by_name
        ? `Ack by ${row.acknowledged_by_name}`
        : "Acknowledged"
      : undefined,
    action_type: actionType,
  };
}
