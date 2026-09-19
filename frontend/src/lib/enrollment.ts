/** Enrollment form state and validation, mirroring the API so errors show before submitting. */

import type { EnrollmentOptions, EnrollmentRequest, Language } from "@/lib/clinicalApi";

export interface EnrollmentDraft {
  patient_name: string;
  mrn: string;
  phone_e164: string;
  language_code: Language;
  date_of_birth: string;
  procedure_code: string;
  surgery_date: string;
  discharge_date: string;
  consent_version: string;
  consent_confirmed: boolean;
  baseline: Record<string, string>;
}

export function emptyDraft(options: EnrollmentOptions): EnrollmentDraft {
  return {
    patient_name: "",
    mrn: "",
    phone_e164: "+91",
    language_code: "en",
    date_of_birth: "",
    procedure_code: options.procedures[0]?.procedure_code ?? "",
    surgery_date: "",
    discharge_date: options.today,
    consent_version: "v1",
    consent_confirmed: false,
    baseline: {},
  };
}

const PHONE = /^\+[1-9][0-9]{7,14}$/;

/** Field name -> message. Empty when the draft can be submitted. */
export function validateEnrollment(draft: EnrollmentDraft, options: EnrollmentOptions): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!draft.patient_name.trim()) errors.patient_name = "Enter the patient's name.";
  if (!draft.mrn.trim()) errors.mrn = "Enter the hospital record number.";
  if (!PHONE.test(draft.phone_e164)) errors.phone_e164 = "Use international format, e.g. +919876543210.";
  if (!draft.procedure_code) errors.procedure_code = "Choose the procedure.";
  if (!draft.surgery_date) errors.surgery_date = "Enter the surgery date.";
  if (!draft.discharge_date) errors.discharge_date = "Enter the discharge date.";
  if (draft.surgery_date && draft.discharge_date && draft.discharge_date < draft.surgery_date) {
    errors.discharge_date = "Discharge cannot be before surgery.";
  }
  if (draft.discharge_date > options.today) errors.discharge_date = "Discharge cannot be in the future.";
  if (draft.date_of_birth && draft.surgery_date && draft.date_of_birth >= draft.surgery_date) {
    errors.date_of_birth = "Date of birth must be before surgery.";
  }
  if (!draft.consent_version.trim()) errors.consent_version = "Enter the consent form version.";
  if (!draft.consent_confirmed) errors.consent_confirmed = "Confirm the patient has consented to monitoring.";

  for (const param of options.baseline_parameters) {
    const raw = draft.baseline[param.code]?.trim();
    if (!raw || param.type === "ordinal") continue;
    const value = Number(raw);
    if (Number.isNaN(value) || (param.value_min !== null && value < param.value_min) ||
        (param.value_max !== null && value > param.value_max)) {
      errors[`baseline.${param.code}`] = `Between ${param.value_min} and ${param.value_max}.`;
    }
  }
  return errors;
}

/** The API payload: blank baseline fields are left out, not sent as zero. */
export function toEnrollmentRequest(draft: EnrollmentDraft, options: EnrollmentOptions): EnrollmentRequest {
  const baseline: Record<string, number | string> = {};
  for (const param of options.baseline_parameters) {
    const raw = draft.baseline[param.code]?.trim();
    if (!raw) continue;
    baseline[param.code] = param.type === "ordinal" ? raw : Number(raw);
  }
  return {
    patient_name: draft.patient_name.trim(),
    mrn: draft.mrn.trim(),
    phone_e164: draft.phone_e164.trim(),
    language_code: draft.language_code,
    date_of_birth: draft.date_of_birth || null,
    procedure_code: draft.procedure_code,
    surgery_date: draft.surgery_date,
    discharge_date: draft.discharge_date,
    consent_version: draft.consent_version.trim(),
    consent_confirmed: true,
    baseline,
  };
}
