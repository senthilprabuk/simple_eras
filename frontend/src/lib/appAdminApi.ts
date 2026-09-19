/** The platform admin area's API: hospitals and scoring rulesets across every tenant. */

import { request } from "@/lib/api";
import type { PrivacyLaw } from "@/lib/clinicalApi";

export type RulesetStatus = "draft" | "approved" | "retired";
export type DisplaySection = "readings" | "checks" | "progress";

export interface PlatformOptions {
  procedures: { procedure_code: string; procedure_name: string; approved_version: string | null }[];
  privacy_laws: PrivacyLaw[];
  timezones: string[];
}

export interface HospitalAccount {
  admin_user_id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface PlatformHospital {
  hospital_id: number;
  hospital_code: string;
  hospital_name: string;
  city: string | null;
  timezone: string;
  ack_window_secs: number;
  privacy_law: PrivacyLaw;
  is_active: boolean;
  procedure_codes: string[];
  account_count: number;
  active_patients: number;
  created_at: string;
}

export interface PlatformHospitalDetail extends PlatformHospital {
  accounts: HospitalAccount[];
}

export interface HospitalFields {
  hospital_name: string;
  city: string | null;
  timezone: string;
  ack_window_secs: number;
  privacy_law: PrivacyLaw;
  is_active: boolean;
  procedure_codes: string[];
}

export interface AccountInput {
  email: string;
  full_name: string;
  role: "admin" | "superadmin";
  password: string;
}

export interface RulesetVersion {
  ruleset_id: number;
  version: string;
  status: RulesetStatus;
  review_at: number;
  critical_at: number;
  max_points_per_parameter: number;
  approved_by: string | null;
  approved_at: string | null;
  notes: string | null;
  created_at: string;
  parameter_count: number;
  active_episodes: number;
  total_episodes: number;
}

export interface ProcedureRulesets {
  procedure_code: string;
  procedure_name: string;
  observation_days: number;
  hospitals_offering: number;
  versions: RulesetVersion[];
}

export interface BindingInput {
  display_section: DisplaySection;
  display_order: number;
  collect_from_day: number;
  collect_to_day: number;
  score_from_day: number;
  score_to_day: number;
  weight: number;
  is_mandatory: boolean;
  question_text: string;
  nurse_script: string | null;
  scoring_config: Record<string, unknown>;
}

export interface RulesetBinding extends BindingInput {
  parameter_code: string;
  parameter_name: string;
  parameter_type: "numeric" | "boolean" | "ordinal";
  unit: string | null;
  scoring_summary: string;
}

export interface AvailableParameter {
  parameter_code: string;
  parameter_name: string;
  parameter_type: "numeric" | "boolean" | "ordinal";
  unit: string | null;
  option_codes: string[];
}

export interface RulesetDetail extends RulesetVersion {
  procedure_code: string;
  procedure_name: string;
  observation_days: number;
  bindings: RulesetBinding[];
  available_parameters: AvailableParameter[];
}

const BASE = "/api/v1/app-admin";
const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });

export const fetchPlatformOptions = () => request<PlatformOptions>(`${BASE}/options`);

export const fetchHospitals = () => request<PlatformHospital[]>(`${BASE}/hospitals`);
export const fetchHospital = (id: number) => request<PlatformHospitalDetail>(`${BASE}/hospitals/${id}`);
export const createHospital = (fields: HospitalFields & { hospital_code: string }) =>
  request<PlatformHospitalDetail>(`${BASE}/hospitals`, json("POST", fields));
export const updateHospital = (id: number, fields: HospitalFields) =>
  request<PlatformHospitalDetail>(`${BASE}/hospitals/${id}`, json("PUT", fields));
export const createHospitalAccount = (id: number, account: AccountInput) =>
  request<PlatformHospitalDetail>(`${BASE}/hospitals/${id}/accounts`, json("POST", account));

export const fetchRulesets = () => request<ProcedureRulesets[]>(`${BASE}/rulesets`);
export const fetchRuleset = (id: number) => request<RulesetDetail>(`${BASE}/rulesets/${id}`);
export const startDraft = (fromId: number, version: string, notes: string | null) =>
  request<RulesetDetail>(`${BASE}/rulesets/${fromId}/drafts`, json("POST", { version, notes }));
export const updateDraft = (
  id: number,
  changes: Partial<Pick<RulesetVersion, "review_at" | "critical_at" | "max_points_per_parameter" | "notes">>,
) => request<RulesetDetail>(`${BASE}/rulesets/${id}`, json("PATCH", changes));
export const saveBinding = (id: number, code: string, binding: BindingInput) =>
  request<RulesetDetail>(`${BASE}/rulesets/${id}/parameters/${code}`, json("PUT", binding));
export const removeBinding = (id: number, code: string) =>
  request<RulesetDetail>(`${BASE}/rulesets/${id}/parameters/${code}`, json("DELETE"));
export const approveDraft = (id: number, approvedBy: string) =>
  request<RulesetDetail>(`${BASE}/rulesets/${id}/approve`, json("POST", { approved_by: approvedBy }));
export const discardDraft = (id: number) => request<void>(`${BASE}/rulesets/${id}`, json("DELETE"));
