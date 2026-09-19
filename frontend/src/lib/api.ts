/**
 * Clinician dashboard API client. Every request after sign-in carries the
 * clinician's own token; a 401 ends the session and returns to sign-in.
 */

import { clearSession, loadSession, saveSession, type Session } from "@/lib/session";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Tier = "emergency" | "critical" | "review" | "missed";
export type Outcome = "reassured" | "plan_adjusted" | "same_day_review" | "emergency";

export interface Reason {
  name: string;
  detail: string | null;
}

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
  tier: Tier;
  reasons: Reason[];
  raised_at: string;
  age_secs: number;
  acknowledged: boolean;
  acknowledged_at: string | null;
  acknowledged_by_name: string | null;
  ack_window_secs: number;
}

export interface QueueResponse {
  items: QueueRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface KpiResponse {
  active_patients: number;
  patients_with_open_alerts: number;
  unresolved_alerts: number;
  unacknowledged_alerts: number;
  ack_compliance_pct: number | null;
  ack_decided_alerts: number;
  ack_window_secs: number;
  missed_checkins_today: number;
  window_days: number;
}

export interface ParameterReading {
  code: string;
  name: string;
  type: "numeric" | "boolean" | "ordinal";
  unit: string | null;
  decimals: number;
  concerning_when_true: boolean | null;
  baseline: number | boolean | string | null;
  current: number | boolean | string | null;
}

export interface EmergencyContact {
  name: string;
  relationship: string;
  phone_e164: string;
}

export interface Address {
  line: string | null;
  city: string | null;
  district: string | null;
  state: string | null;
  postal_code: string | null;
}

export interface ConsentDecision {
  code: "remote_monitoring" | "data_processing" | "contact_sharing";
  granted: boolean;
  privacy_law: string;
  recorded_at: string;
}

export interface BodyMeasurements {
  height_cm: number | null;
  weight_kg: number | null;
  bmi: number | null;
  bp_systolic: number | null;
  bp_diastolic: number | null;
}

export interface EpisodeSummary {
  episode_id: string;
  patient_name: string;
  mrn: string | null;
  phone_e164: string;
  alt_phone_e164: string | null;
  email: string | null;
  gender: string;
  date_of_birth: string | null;
  age_years: number | null;
  address: Address | null;
  emergency_contacts: EmergencyContact[];
  hospital_name: string;
  procedure_code: string;
  procedure_name: string;
  discharge_date: string;
  post_op_day: number;
  status: string;
  ruleset_version: string;
  checkin_window_start: string;
  checkin_window_end: string;
  consents: ConsentDecision[];
  body: BodyMeasurements;
  latest_check_in: {
    check_in_id: string;
    day_after_discharge: number;
    submitted_at: string;
    source: string;
    photo_submitted: boolean;
  } | null;
  readings: ParameterReading[];
}

export interface HospitalChoice {
  hospital_id: number;
  hospital_name: string;
}

export interface Health {
  status: string;
  scheduler_running: boolean;
  notification_provider: "disabled" | "log";
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

/**
 * Sign-in lives on its own page; `next` brings the clinician back afterwards.
 * A full page load, not client routing, so no patient data survives in memory.
 */
export function redirectToLogin(): void {
  if (typeof window === "undefined" || window.location.pathname.startsWith("/login")) return;
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.replace(`/login?next=${next}`);
}

function describe(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String(detail.message);
  if (Array.isArray(detail)) return "Some details were not valid. Check the form and try again.";
  return `Request failed (${status})`;
}

export async function request<T>(path: string, init: RequestInit = {}, authenticated = true): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (authenticated) {
    const session = loadSession();
    if (!session) {
      redirectToLogin();
      throw new ApiError(401, "Please sign in.");
    }
    headers.Authorization = `Bearer ${session.token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check the connection and try again.");
  }

  if (res.status === 401 && authenticated) {
    clearSession();
    redirectToLogin();
    throw new ApiError(401, "Your session has ended. Please sign in again.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, describe(body.detail, res.status), body.detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function signIn(email: string, password: string, hospitalId?: number): Promise<Session> {
  const data = await request<{
    access_token: string;
    expires_in: number;
    admin_user_id: string;
    hospital_id: number | null;
    hospital_name: string | null;
    full_name: string;
    role: string;
  }>(
    "/api/v1/auth/login",
    { method: "POST", body: JSON.stringify({ email, password, hospital_id: hospitalId }) },
    false,
  );
  const session: Session = {
    token: data.access_token,
    expiresAt: Date.now() + data.expires_in * 1000,
    adminUserId: data.admin_user_id,
    hospitalId: data.hospital_id,
    hospitalName: data.hospital_name,
    fullName: data.full_name,
    role: data.role,
  };
  saveSession(session);
  return session;
}

/** Hospitals offered when the same account exists at several; only sent after the password matched. */
export function hospitalChoices(error: unknown): HospitalChoice[] | null {
  if (!(error instanceof ApiError) || error.status !== 400) return null;
  const detail = error.detail as { hospitals?: HospitalChoice[] } | undefined;
  return detail?.hospitals ?? null;
}

export function fetchQueue(limit = 200): Promise<QueueResponse> {
  return request<QueueResponse>(`/api/v1/dashboard/queue?limit=${limit}`);
}

export function fetchKpis(windowDays = 7): Promise<KpiResponse> {
  return request<KpiResponse>(`/api/v1/dashboard/kpis?window_days=${windowDays}`);
}

export function fetchEpisodeSummary(episodeId: string): Promise<EpisodeSummary> {
  return request<EpisodeSummary>(`/api/v1/episodes/${episodeId}/summary`);
}

export function fetchHealth(): Promise<Health> {
  return request<Health>("/health", {}, false);
}

export function acknowledgeAlert(alertId: string): Promise<unknown> {
  return request(`/api/v1/alerts/${alertId}/acknowledge`, { method: "POST" });
}

export function resolveAlert(alertId: string, outcome: Outcome, note: string): Promise<unknown> {
  return request(`/api/v1/alerts/${alertId}/resolve`, {
    method: "POST",
    body: JSON.stringify({ outcome, note: note.trim() || null }),
  });
}
