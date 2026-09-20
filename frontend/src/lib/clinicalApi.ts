/** Endpoints behind the menu screens: patients, alerts, enrollment, rulesets, hospital, templates, reports, settings. */

import { request, type Outcome, type Reason, type Tier } from "@/lib/api";

/* ------------------------------------------------------------ patients */

export type EpisodeStatus = "active" | "completed" | "withdrawn";

/** Which knee was replaced. Null for episodes enrolled before it was captured. */
export type OperativeSide = "left" | "right" | "bilateral";

/**
 * The adjective only. It is composed with the episode's own procedure code at
 * the point of display — "Right TKR" — rather than baked in here, because the
 * hospital may monitor more than one procedure and a hip would read wrongly.
 */
export const SIDE_WORD: Record<OperativeSide, string> = {
  left: "Left",
  right: "Right",
  bilateral: "Bilateral",
};

export function sideLabel(side: OperativeSide | null, procedureCode: string): string {
  return side ? `${SIDE_WORD[side]} ${procedureCode}` : procedureCode;
}

/**
 * Whether today's check-in is in. The server decides this, because "today" is
 * the hospital's own date and a workstation in another timezone would disagree
 * about which post-operative day it is.
 */
export type CheckInToday = "done" | "pending" | "none_yet" | "not_due";

export const CHECK_IN_TODAY: Record<CheckInToday, { label: string; className: string }> = {
  done: { label: "Done today", className: "bg-primary/10 text-primary" },
  pending: { label: "Pending today", className: "bg-tertiary/15 text-tertiary" },
  none_yet: { label: "None yet", className: "bg-surface-bright text-on-surface-variant" },
  not_due: { label: "Not due", className: "bg-surface-bright text-outline" },
};

export interface PatientListItem {
  episode_id: string;
  patient_id: string;
  patient_name: string;
  mrn: string | null;
  phone_e164: string | null;
  language_code: string;
  procedure_code: string;
  operative_side: OperativeSide | null;
  discharge_date: string;
  monitoring_ends_on: string;
  status: EpisodeStatus;
  post_op_day: number;
  enrolled_at: string;
  enrolled_by_name: string | null;
  last_check_in_day: number | null;
  last_check_in_at: string | null;
  check_in_today: CheckInToday;
  check_in_days: number;
  expected_check_in_days: number;
  adherence_pct: number | null;
  open_alerts: number;
  top_open_tier: Tier | null;
}

export interface PatientListResponse {
  items: PatientListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface TrendPoint {
  day: number;
  date: string;
  value: number | null;
  threshold: number | null;
  collected: boolean;
}

export interface Trend {
  code: string;
  name: string;
  unit: string | null;
  decimals: number;
  baseline: number | null;
  threshold_direction: "above" | "below" | null;
  scoring_rule: string;
  points: TrendPoint[];
}

export interface ObservationCell {
  value: boolean | null;
  asked: boolean;
}

export interface ObservationColumn {
  code: string;
  name: string;
  question_text: string | null;
  is_emergency: boolean;
}

export interface ObservationRow {
  day: number;
  date: string;
  checked_in: boolean;
  source: string | null;
  values: Record<string, ObservationCell>;
}

export interface PatientTimeline {
  episode_id: string;
  post_op_day: number;
  trends: Trend[];
  observation_columns: ObservationColumn[];
  observations: ObservationRow[];
}

export function fetchPatients(params: {
  status: EpisodeStatus | "all";
  search?: string;
  sort?: "priority" | "recent" | "name";
  limit?: number;
}): Promise<PatientListResponse> {
  const query = new URLSearchParams({
    status: params.status,
    search: params.search ?? "",
    sort: params.sort ?? "priority",
    limit: String(params.limit ?? 200),
  });
  return request<PatientListResponse>(`/api/v1/patients?${query}`);
}

export function fetchPatientTimeline(episodeId: string): Promise<PatientTimeline> {
  return request<PatientTimeline>(`/api/v1/patients/${episodeId}/timeline`);
}

/* -------------------------------------------------------------- alerts */

export type AlertStatus = "open" | "acknowledged" | "resolved" | "expired";

export interface AlertHistoryItem {
  alert_id: string;
  episode_id: string;
  patient_name: string;
  mrn: string | null;
  phone_e164: string | null;
  operative_side: OperativeSide | null;
  procedure_code: string;
  tier: Tier;
  status: AlertStatus;
  day_after_discharge: number;
  reasons: Reason[];
  raised_at: string;
  escalated_at: string | null;
  acknowledged_at: string | null;
  acknowledged_by_name: string | null;
  ack_secs: number | null;
  ack_window_secs: number;
  resolved_at: string | null;
  resolved_by_name: string | null;
  outcome: Outcome | null;
  outcome_note: string | null;
}

export interface AlertHistoryResponse {
  items: AlertHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

export function fetchAlertHistory(params: {
  status: AlertStatus | "all";
  tier: Tier | "all";
  days: number;
  episodeId?: string | null;
  limit?: number;
  offset?: number;
}): Promise<AlertHistoryResponse> {
  const query = new URLSearchParams({
    status: params.status,
    tier: params.tier,
    days: String(params.days),
    limit: String(params.limit ?? 100),
    offset: String(params.offset ?? 0),
  });
  if (params.episodeId) query.set("episode_id", params.episodeId);
  return request<AlertHistoryResponse>(`/api/v1/alerts?${query}`);
}

/* ---------------------------------------------------------- enrollment */

export type Language = "en" | "ta" | "hi";

export interface BaselineParameter {
  code: string;
  name: string;
  type: "numeric" | "ordinal";
  unit: string | null;
  value_min: number | null;
  value_max: number | null;
  decimals: number;
  options: { code: string; label: string; rank: number }[];
}

export type Gender = "male" | "female" | "other" | "unknown";
export type Relationship =
  | "spouse"
  | "son"
  | "daughter"
  | "sibling"
  | "parent"
  | "other_family"
  | "friend"
  | "caregiver";
export type CheckInWindowCode = "morning" | "midday" | "evening";
export type PrivacyLaw = "DPDP-2023" | "HIPAA";

export interface CheckInWindow {
  code: CheckInWindowCode;
  label: string;
  start: string;
  end: string;
}

export interface EnrollmentOptions {
  procedures: { procedure_code: string; procedure_name: string; observation_days: number; ruleset_version: string }[];
  languages: Language[];
  baseline_parameters: BaselineParameter[];
  checkin_windows: CheckInWindow[];
  privacy_law: PrivacyLaw;
  today: string;
}

export interface EmergencyContactInput {
  name: string;
  relationship: Relationship;
  phone_e164: string;
}

export interface EnrollmentRequest {
  patient_name: string;
  mrn: string;
  phone_e164: string;
  language_code: Language;
  date_of_birth: string | null;
  gender: Gender;
  address: { line: string; city: string | null; district: string; state: string | null; postal_code: string };
  alt_phone_e164: string | null;
  email: string | null;
  emergency_contacts: EmergencyContactInput[];
  procedure_code: string;
  operative_side: OperativeSide;
  surgery_date: string;
  discharge_date: string;
  checkin_window: CheckInWindowCode;
  consent_version: string;
  consent_confirmed: true;
  data_processing_consent: true;
  contact_sharing_consent: boolean;
  baseline: Record<string, number | string>;
}

export interface EnrollmentResponse {
  episode_id: string;
  patient_id: string;
  returning_patient: boolean;
  monitoring_ends_on: string;
  post_op_day: number;
  baseline_recorded: number;
}

export function fetchEnrollmentOptions(): Promise<EnrollmentOptions> {
  return request<EnrollmentOptions>("/api/v1/enrollment/options");
}

export function enrollPatient(body: EnrollmentRequest): Promise<EnrollmentResponse> {
  return request<EnrollmentResponse>("/api/v1/enrollment", { method: "POST", body: JSON.stringify(body) });
}

/* ------------------------------------------------------------ rulesets */

/** Which way a numeric measure goes wrong: a fever rises, oxygen falls. */
export type RuleDirection = "higher_is_worse" | "higher_is_better";

export const DIRECTION_LABELS: Record<RuleDirection, string> = {
  higher_is_worse: "Higher is worse",
  higher_is_better: "Higher is better",
};

export interface RulesetSummary {
  ruleset_id: number;
  procedure_code: string;
  procedure_name: string;
  version: string;
  status: "draft" | "approved" | "retired";
  review_at: number;
  critical_at: number;
  max_points_per_parameter: number;
  approved_by: string | null;
  approved_at: string | null;
  notes: string | null;
  parameter_count: number;
  episodes_using: number;
}

export interface RulesetParameter {
  code: string;
  name: string;
  type: string;
  unit: string | null;
  section: string;
  display_order: number;
  collect_from_day: number;
  collect_to_day: number;
  score_from_day: number;
  score_to_day: number;
  weight: number;
  is_mandatory: boolean;
  is_emergency: boolean;
  question_text: string | null;
  scoring_summary: string;
  direction: RuleDirection | null;
}

export interface RulesetDetail extends RulesetSummary {
  observation_days: number;
  /** Signals that read every measure at once rather than belonging to one. */
  composite_summary: string[];
  parameters: RulesetParameter[];
}

export function fetchRulesets(): Promise<RulesetSummary[]> {
  return request<RulesetSummary[]>("/api/v1/rulesets");
}

export function fetchRuleset(rulesetId: number): Promise<RulesetDetail> {
  return request<RulesetDetail>(`/api/v1/rulesets/${rulesetId}`);
}

/* ------------------------------------------------------------ hospital */

export interface HospitalProfile {
  hospital_id: number;
  hospital_code: string;
  hospital_name: string;
  city: string | null;
  timezone: string;
  ack_window_secs: number;
  is_active: boolean;
  procedures: {
    procedure_code: string;
    procedure_name: string;
    observation_days: number;
    enabled_on: string;
    is_active: boolean;
  }[];
  stats: {
    active_patients: number;
    completed_patients: number;
    active_clinicians: number;
    unresolved_alerts: number;
    check_ins_last_7_days: number;
  };
}

export interface HospitalUpdate {
  hospital_name?: string;
  city?: string;
  timezone?: string;
  ack_window_secs?: number;
}

export function fetchHospital(): Promise<HospitalProfile> {
  return request<HospitalProfile>("/api/v1/hospital");
}

export function updateHospital(changes: HospitalUpdate): Promise<HospitalProfile> {
  return request<HospitalProfile>("/api/v1/hospital", { method: "PATCH", body: JSON.stringify(changes) });
}

/* ----------------------------------------------------------- templates */

export type TemplateKey =
  | "enrollment_welcome"
  | "checkin_reminder"
  | "missed_checkin"
  | "urgent_guidance"
  | "checkin_confirmation";

export interface TemplateEntry {
  template_key: TemplateKey;
  language_code: Language;
  body: string | null;
  is_active: boolean;
  updated_at: string | null;
  updated_by_name: string | null;
}

export interface TemplateCatalogue {
  templates: TemplateEntry[];
  purposes: Record<TemplateKey, string>;
  placeholders: Record<string, string>;
}

export function fetchTemplates(): Promise<TemplateCatalogue> {
  return request<TemplateCatalogue>("/api/v1/templates");
}

export function saveTemplate(key: TemplateKey, language: Language, body: string, isActive: boolean): Promise<TemplateEntry> {
  return request<TemplateEntry>(`/api/v1/templates/${key}/${language}`, {
    method: "PUT",
    body: JSON.stringify({ body, is_active: isActive }),
  });
}

/* ------------------------------------------------------------- reports */

export interface ReportResponse {
  days: number;
  ack_window_secs: number;
  summary: {
    alerts_raised: number;
    escalated: number;
    median_ack_secs: number | null;
    ack_compliance_pct: number | null;
    adherence_pct: number | null;
  };
  alerts_by_week: { week_start: string; counts: Record<Tier, number> }[];
  ack_by_week: { week_start: string; decided: number; met: number; pct: number | null }[];
  outcomes: Record<Outcome, number>;
  adherence_by_day: { date: string; expected: number; submitted: number; pct: number | null }[];
}

export function fetchReport(days: number): Promise<ReportResponse> {
  return request<ReportResponse>(`/api/v1/reports?days=${days}`);
}

/* ------------------------------------------------ clinicians & account */

export type Role = "admin" | "superadmin";

export interface Clinician {
  admin_user_id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export function fetchClinicians(): Promise<Clinician[]> {
  return request<Clinician[]>("/api/v1/clinicians");
}

export function createClinician(body: { email: string; full_name: string; role: Role; password: string }): Promise<Clinician> {
  return request<Clinician>("/api/v1/clinicians", { method: "POST", body: JSON.stringify(body) });
}

export function updateClinician(id: string, changes: { role?: Role; is_active?: boolean }): Promise<Clinician> {
  return request<Clinician>(`/api/v1/clinicians/${id}`, { method: "PATCH", body: JSON.stringify(changes) });
}

export function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return request<void>("/api/v1/account/password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

/* ----------------------------------------------------------- whatsapp account */

export interface WhatsAppAccount {
  account_id: string;
  hospital_id: number;
  display_name: string;
  display_phone_number: string;
  phone_number_id: string;
  waba_id: string;
  meta_app_id: string | null;
  access_token_masked: string;
  verify_token: string;
  health_status: "healthy" | "invalid_token" | "rate_limited" | "unverified";
  is_active: boolean;
  qr_code_url: string;
  click_to_chat_url: string;
  webhook_url: string;
  created_at: string;
}

export interface SaveWhatsAppAccountPayload {
  display_phone_number?: string;
  display_name?: string;
  phone_number_id: string;
  waba_id: string;
  access_token?: string;
  verify_token: string;
  meta_app_id?: string;
}

export interface TestSendResponse {
  status: string;
  message_id?: string;
  error?: string;
}

export function fetchWhatsAppAccount(): Promise<WhatsAppAccount | null> {
  return request<WhatsAppAccount | null>("/api/v1/whatsapp/account");
}

export function saveWhatsAppAccount(payload: SaveWhatsAppAccountPayload): Promise<WhatsAppAccount> {
  return request<WhatsAppAccount>("/api/v1/whatsapp/account", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function disconnectWhatsAppAccount(): Promise<void> {
  return request<void>("/api/v1/whatsapp/account", { method: "DELETE" });
}

export function sendTestWhatsAppMessage(toPhone: string, message?: string): Promise<TestSendResponse> {
  return request<TestSendResponse>("/api/v1/whatsapp/test", {
    method: "POST",
    body: JSON.stringify({ to_phone: toPhone, message }),
  });
}
