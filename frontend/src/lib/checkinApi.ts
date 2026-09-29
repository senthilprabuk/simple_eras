/**
 * Patient check-in API client.
 * The form is built by the backend from the episode's approved ruleset, so the
 * questions shown depend on the patient's post-op day.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface EpisodeOption {
  episode_id: string;
  patient_name: string;
  mrn: string | null;
  procedure_code: string;
  post_op_day: number;
  monitoring_ends_on: string;
  checked_in_today: boolean;
}

export interface OrdinalOption {
  code: string;
  label: string;
  rank: number;
}

export interface FormParameter {
  parameter_id: number;
  code: string;
  name: string;
  question_text: string;
  type: "numeric" | "boolean" | "ordinal";
  section: string;
  unit: string | null;
  value_min: number | null;
  value_max: number | null;
  decimals: number;
  is_mandatory: boolean;
  is_emergency: boolean;
  is_scored_today: boolean;
  options: OrdinalOption[];
}

export interface FormSection {
  key: string;
  parameters: FormParameter[];
}

export interface EpisodeContext {
  episode_id: string;
  patient_name: string;
  first_name: string;
  mrn: string | null;
  hospital_name: string;
  /** Dialled when the patient reports an emergency symptom; null until the hospital sets one. */
  hospital_emergency_phone: string | null;
  procedure_code: string;
  actual_post_op_day: number;
  monitoring_ends_on: string;
}

export interface CheckInForm {
  episode: EpisodeContext;
  ruleset_id: number;
  effective_day: number;
  simulated: boolean;
  /** Language of the questions, names and options: en, ta or hi. */
  language: string;
  /** The language the patient enrolled in. */
  patient_language: string;
  already_submitted_today: boolean;
  sections: FormSection[];
}

export interface CheckInReceipt {
  check_in_id: string;
  episode_id: string;
  day_after_discharge: number;
  source: string;
  submitted_at: string;
  values_recorded: number;
  superseded_count: number;
  duplicate: boolean;
  /** The WhatsApp reply to the patient: null when none was due (every check-in not made through the patient's link). */
  patient_message_status: "sent" | "queued" | "failed" | null;
}

export type AnswerValue = number | boolean | string | null;
export type Answers = Record<string, AnswerValue>;

/** The server answered with an error; a network failure is a TypeError from fetch instead. */
export class CheckInRequestError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, init);
  if (!res.ok) {
    // A check-in link's detail (expired, from an earlier day) is written for the patient.
    const body = await res.json().catch(() => ({}));
    throw new CheckInRequestError(
      typeof body.detail === "string" ? body.detail : `${res.status} ${res.statusText}`,
      res.status
    );
  }
  return res.json();
}

export function fetchEpisodes(): Promise<EpisodeOption[]> {
  return getJson<EpisodeOption[]>("/api/v1/checkin/episodes");
}

export function fetchCheckInForm(episodeId: string, day?: number, lang?: string): Promise<CheckInForm> {
  const query = `${day === undefined ? "" : `&day=${day}`}${lang ? `&lang=${lang}` : ""}`;
  return getJson<CheckInForm>(`/api/v1/checkin/form?episode_id=${episodeId}${query}`);
}

/** The token goes in a header, not the URL, so no server or proxy access log records it. */
export function fetchCheckInFormByToken(token: string, lang?: string): Promise<CheckInForm> {
  return getJson<CheckInForm>(`/api/v1/checkin/form${lang ? `?lang=${lang}` : ""}`, {
    headers: { "X-Checkin-Token": token },
  });
}

export async function submitCheckIn(input: {
  episodeId: string;
  day: number;
  simulated: boolean;
  idempotencyKey: string;
  token?: string;
  parameters: FormParameter[];
  answers: Answers;
}): Promise<CheckInReceipt> {
  const values = input.parameters
    .filter((p) => isAnswered(input.answers[p.code]))
    .map((p) => {
      const value = input.answers[p.code];
      if (p.type === "boolean") return { parameter_id: p.parameter_id, value_bool: value as boolean };
      if (p.type === "ordinal") return { parameter_id: p.parameter_id, value_code: value as string };
      return { parameter_id: p.parameter_id, value_num: value as number };
    });

  const res = await fetch(`${API_BASE_URL}/api/v1/checkin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      episode_id: input.episodeId,
      day_after_discharge: input.day,
      simulated: input.simulated,
      idempotency_key: input.idempotencyKey,
      token: input.token,
      values,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ? JSON.stringify(body.detail) : `Submission failed (${res.status})`);
  }
  return res.json();
}

/* ------------------------------------------------- presentation helpers */

export const SECTION_META: Record<string, { title: string; intro?: string }> = {
  readings: { title: "Your readings" },
  checks: {
    title: "Symptom checks",
    intro: "Since yesterday, have you noticed any of these?",
  },
  progress: { title: "Getting moving" },
};

const ICONS: Record<string, string> = {
  temp_c: "thermometer",
  hr: "ecg_heart",
  spo2: "spo2",
  pain: "mood",
  steps: "directions_walk",
  calf_pain: "personal_injury",
  breathless: "pulmonology",
  drainage: "healing",
  chills: "severe_cold",
  weight_bear: "do_not_step",
  knee_bend: "accessibility_new",
  walk_aid: "elderly",
};

/** Where the stepper starts when a patient first taps it. Presentation only — never a stored answer. */
const ANCHORS: Record<string, number> = { temp_c: 36.8, hr: 72, spo2: 97, steps: 200 };

const STEP_SIZE: Record<string, number> = { steps: 50 };

export function iconFor(param: FormParameter): string {
  return ICONS[param.code] ?? "help";
}

export function anchorFor(param: FormParameter): number {
  if (ANCHORS[param.code] !== undefined) return ANCHORS[param.code];
  const min = param.value_min ?? 0;
  const max = param.value_max ?? 10;
  return Math.round((min + max) / 2);
}

export function stepFor(param: FormParameter): number {
  if (STEP_SIZE[param.code] !== undefined) return STEP_SIZE[param.code];
  return param.decimals > 0 ? 0.1 : 1;
}

export function sectionTitle(key: string): string {
  return SECTION_META[key]?.title ?? key;
}

export function isAnswered(value: AnswerValue): boolean {
  return value !== null && value !== undefined;
}

export interface AnswerWords {
  notAnswered: string;
  yes: string;
  no: string;
}

const ENGLISH_ANSWER_WORDS: AnswerWords = { notAnswered: "Not answered", yes: "Yes", no: "No" };

export function formatAnswer(param: FormParameter, value: AnswerValue, words: AnswerWords = ENGLISH_ANSWER_WORDS): string {
  if (!isAnswered(value)) return words.notAnswered;
  if (param.type === "boolean") return value ? words.yes : words.no;
  if (param.type === "ordinal") {
    return param.options.find((o) => o.code === value)?.label ?? String(value);
  }
  const text = Number(value).toFixed(param.decimals);
  return param.unit ? `${text} ${param.unit}` : text;
}

/**
 * A blank answer is unknown, never "no". A yes/no symptom question can always be
 * answered, so it must be, as must anything the ruleset marks mandatory; a reading
 * the patient cannot take may be skipped, but only once they have seen what is missing.
 */
export function isRequired(param: FormParameter): boolean {
  return param.type === "boolean" || param.is_mandatory;
}

export function unansweredIn(section: FormSection, answers: Answers): { required: FormParameter[]; optional: FormParameter[] } {
  const blank = section.parameters.filter((p) => !isAnswered(answers[p.code]));
  return { required: blank.filter(isRequired), optional: blank.filter((p) => !isRequired(p)) };
}

/** Red flags that need a phone call now rather than routine triage. */
export function urgentAnswers(sections: FormSection[], answers: Answers): FormParameter[] {
  return sections
    .flatMap((s) => s.parameters)
    .filter((p) => p.is_emergency && answers[p.code] === true);
}
