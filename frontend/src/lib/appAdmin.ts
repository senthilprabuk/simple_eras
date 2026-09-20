/** Form state and checks for the admin screens, mirroring the API so mistakes show before saving. */

import type { PrivacyLaw, RuleDirection } from "@/lib/clinicalApi";
import type {
  AvailableParameter,
  BindingInput,
  DisplaySection,
  HospitalFields,
  PlatformHospital,
  RulesetBinding,
} from "@/lib/appAdminApi";

export interface HospitalDraft {
  hospital_code: string;
  hospital_name: string;
  city: string;
  timezone: string;
  ack_window_mins: string;
  privacy_law: PrivacyLaw;
  is_active: boolean;
  procedure_codes: string[];
}

export function hospitalDraft(hospital?: PlatformHospital): HospitalDraft {
  return {
    hospital_code: hospital?.hospital_code ?? "",
    hospital_name: hospital?.hospital_name ?? "",
    city: hospital?.city ?? "",
    timezone: hospital?.timezone ?? "Asia/Kolkata",
    ack_window_mins: String((hospital?.ack_window_secs ?? 900) / 60),
    privacy_law: hospital?.privacy_law ?? "DPDP-2023",
    is_active: hospital?.is_active ?? true,
    procedure_codes: hospital?.procedure_codes ?? [],
  };
}

export function validateHospital(draft: HospitalDraft, isNew: boolean, timezones: string[]): Record<string, string> {
  const errors: Record<string, string> = {};
  if (isNew && !/^[A-Z0-9][A-Z0-9-]{1,19}$/.test(draft.hospital_code.trim().toUpperCase())) {
    errors.hospital_code = "2–20 letters, digits or dashes, e.g. CBE-02.";
  }
  if (!draft.hospital_name.trim()) errors.hospital_name = "Enter the hospital's name.";
  if (timezones.length > 0 && !timezones.includes(draft.timezone.trim())) {
    errors.timezone = "Choose a time zone from the list, e.g. Asia/Kolkata.";
  }
  const minutes = Number(draft.ack_window_mins);
  if (!Number.isInteger(minutes) || minutes < 1 || minutes > 120) {
    errors.ack_window_mins = "A whole number of minutes from 1 to 120.";
  }
  return errors;
}

export function toHospitalFields(draft: HospitalDraft): HospitalFields {
  return {
    hospital_name: draft.hospital_name.trim(),
    city: draft.city.trim() || null,
    timezone: draft.timezone.trim(),
    ack_window_secs: Number(draft.ack_window_mins) * 60,
    privacy_law: draft.privacy_law,
    is_active: draft.is_active,
    procedure_codes: draft.procedure_codes,
  };
}

/** A version name one step on from the newest, as a suggestion: 1.0.0 -> 1.1.0. */
export function suggestVersion(existing: string[]): string {
  const numbered = existing
    .map((v) => v.split(".").map(Number))
    .filter((parts) => parts.length === 3 && parts.every(Number.isInteger));
  if (numbered.length === 0) return "1.0.0";
  const [major, minor] = numbered.reduce((a, b) => (a[0] !== b[0] ? (a[0] > b[0] ? a : b) : a[1] >= b[1] ? a : b));
  let next = `${major}.${minor + 1}.0`;
  for (let bump = minor + 2; existing.includes(next); bump++) next = `${major}.${bump}.0`;
  return next;
}

export interface BindingDraft {
  display_section: DisplaySection;
  display_order: string;
  collect_from_day: string;
  collect_to_day: string;
  score_from_day: string;
  score_to_day: string;
  weight: string;
  is_mandatory: boolean;
  question_text: string;
  nurse_script: string;
  /** Empty when the measure is not numeric, where "higher" means nothing. */
  direction: RuleDirection | "";
  scoring_config: string;
}

/** A starting rule for a newly added measure, to be edited rather than typed from nothing. */
export function starterRule(parameter: AvailableParameter): Record<string, unknown> {
  if (parameter.parameter_type === "boolean") return { binary_score: 1 };
  if (parameter.parameter_type === "ordinal") return { milestone: { "14": parameter.option_codes[0] ?? "" }, score: 1 };
  return { direction: "higher_is_worse", bands: [[0, 10, 0], [10, 99, 1]] };
}

/**
 * The rule as the editor shows it: direction is picked from a list, the rest is
 * typed as JSON. They are put back together on save, so the author never has to
 * spell an enum correctly in a text box.
 */
function splitRule(config: Record<string, unknown>, parameterType: string): Pick<BindingDraft, "direction" | "scoring_config"> {
  const { direction, ...rest } = config;
  return {
    direction: parameterType === "numeric" ? ((direction as RuleDirection) ?? "higher_is_worse") : "",
    scoring_config: JSON.stringify(rest, null, 2),
  };
}

export function bindingDraft(binding: RulesetBinding): BindingDraft {
  return {
    display_section: binding.display_section,
    display_order: String(binding.display_order),
    collect_from_day: String(binding.collect_from_day),
    collect_to_day: String(binding.collect_to_day),
    score_from_day: String(binding.score_from_day),
    score_to_day: String(binding.score_to_day),
    weight: String(binding.weight),
    is_mandatory: binding.is_mandatory,
    question_text: binding.question_text ?? "",
    nurse_script: binding.nurse_script ?? "",
    ...splitRule(binding.scoring_config, binding.parameter_type),
  };
}

export function newBindingDraft(parameter: AvailableParameter, observationDays: number, nextOrder: number): BindingDraft {
  return {
    display_section: parameter.parameter_type === "boolean" ? "checks" : parameter.parameter_type === "ordinal" ? "progress" : "readings",
    display_order: String(nextOrder),
    collect_from_day: "0",
    collect_to_day: String(observationDays),
    score_from_day: "0",
    score_to_day: String(observationDays),
    weight: "1",
    is_mandatory: false,
    question_text: "",
    nurse_script: "",
    ...splitRule(starterRule(parameter), parameter.parameter_type),
  };
}

/** The API payload, or the field errors that stop it being sent. The server checks the rule itself. */
export function parseBinding(
  draft: BindingDraft,
  observationDays: number,
): { binding: BindingInput; errors: null } | { binding: null; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const whole = (key: keyof BindingDraft, min: number, max: number, label: string) => {
    const value = Number(draft[key]);
    if (String(draft[key]).trim() === "" || !Number.isInteger(value) || value < min || value > max) {
      errors[key] = `${label}: a whole number from ${min} to ${max}.`;
    }
    return value;
  };
  const order = whole("display_order", 1, 99, "Position");
  const cFrom = whole("collect_from_day", 0, observationDays, "Asked from");
  const cTo = whole("collect_to_day", 0, observationDays, "Asked until");
  const sFrom = whole("score_from_day", 0, observationDays, "Scored from");
  const sTo = whole("score_to_day", 0, observationDays, "Scored until");
  const weight = whole("weight", 0, 10, "Weight");
  if (!errors.collect_to_day && !errors.collect_from_day && cTo < cFrom) errors.collect_to_day = "Must be on or after the first day asked.";
  if (!errors.score_to_day && !errors.score_from_day && sTo < sFrom) errors.score_to_day = "Must be on or after the first day scored.";
  if (!errors.score_from_day && !errors.collect_from_day && sFrom < cFrom) errors.score_from_day = "Answers can only be scored on days they are asked.";
  if (!errors.score_to_day && !errors.collect_to_day && sTo > cTo) errors.score_to_day = "Answers can only be scored on days they are asked.";
  if (!draft.question_text.trim()) errors.question_text = "Enter what the patient is asked.";

  let config: unknown = null;
  try {
    config = JSON.parse(draft.scoring_config);
  } catch {
    errors.scoring_config = "Not valid JSON. Check the brackets, commas and quotes.";
  }
  if (!errors.scoring_config && (typeof config !== "object" || config === null || Array.isArray(config))) {
    errors.scoring_config = "The rule must be a JSON object, e.g. {\"binary_score\": 3}.";
  }
  if (!errors.scoring_config && "direction" in (config as Record<string, unknown>)) {
    errors.scoring_config = "Set which way is worse with the list above, not in the JSON.";
  }

  if (Object.keys(errors).length > 0) return { binding: null, errors };
  return {
    binding: {
      display_section: draft.display_section,
      display_order: order,
      collect_from_day: cFrom,
      collect_to_day: cTo,
      score_from_day: sFrom,
      score_to_day: sTo,
      weight,
      is_mandatory: draft.is_mandatory,
      question_text: draft.question_text.trim(),
      nurse_script: draft.nurse_script.trim() || null,
      scoring_config: draft.direction
        ? { direction: draft.direction, ...(config as Record<string, unknown>) }
        : (config as Record<string, unknown>),
    },
    errors: null,
  };
}
