/** Enrollment form state and validation, mirroring the API so errors show before submitting. */

import type {
  CheckInWindowCode,
  EnrollmentOptions,
  EnrollmentRequest,
  Gender,
  Language,
  OperativeSide,
  Relationship,
} from "@/lib/clinicalApi";

export const MAX_CONTACTS = 3;

/** Measured once at enrollment and never asked again, unlike the discharge readings. */
export const BODY_CODES = ["height_cm", "weight_kg", "bp_sys", "bp_dia"];

export interface ContactDraft {
  name: string;
  relationship: Relationship | "";
  phone_e164: string;
}

export interface EnrollmentDraft {
  patient_name: string;
  mrn: string;
  phone_e164: string;
  language_code: Language;
  date_of_birth: string;
  gender: Gender | "";
  address_line: string;
  address_city: string;
  address_district: string;
  address_state: string;
  address_postal_code: string;
  alt_phone_e164: string;
  email: string;
  contacts: ContactDraft[];
  procedure_code: string;
  // No default: which knee it is cannot be guessed, and an unset select is
  // what makes the clinician answer rather than accept whatever was first.
  operative_side: OperativeSide | "";
  surgery_date: string;
  discharge_date: string;
  checkin_window: CheckInWindowCode;
  consent_version: string;
  consent_confirmed: boolean;
  data_processing_consent: boolean;
  contact_sharing_consent: "" | "yes" | "no";
  baseline: Record<string, string>;
}

export const emptyContact = (): ContactDraft => ({ name: "", relationship: "", phone_e164: "+91" });

export function emptyDraft(options: EnrollmentOptions): EnrollmentDraft {
  return {
    patient_name: "",
    mrn: "",
    phone_e164: "+91",
    language_code: "en",
    date_of_birth: "",
    gender: "",
    address_line: "",
    address_city: "",
    address_district: "",
    address_state: "",
    address_postal_code: "",
    alt_phone_e164: "",
    email: "",
    contacts: [emptyContact()],
    procedure_code: options.procedures[0]?.procedure_code ?? "",
    operative_side: "",
    surgery_date: "",
    discharge_date: options.today,
    checkin_window: options.checkin_windows[0]?.code ?? "morning",
    consent_version: "v1",
    consent_confirmed: false,
    data_processing_consent: false,
    contact_sharing_consent: "",
    baseline: {},
  };
}

const PHONE = /^\+[1-9][0-9]{7,14}$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const POSTAL_CODE = /^[A-Za-z0-9 -]{3,10}$/;

/** Numbers are typed the way they are printed: "+91 98765 43210", "+91-98765-43210". */
export function normalisePhone(value: string): string {
  return value.replace(/[\s\-().]/g, "");
}

/** A phone box left at its "+91" prompt counts as blank. */
function isBlankPhone(value: string): boolean {
  return /^\+?\d{0,3}$/.test(normalisePhone(value));
}

export function bmi(heightCm: string | undefined, weightKg: string | undefined): number | null {
  const h = Number(heightCm);
  const w = Number(weightKg);
  if (!heightCm?.trim() || !weightKg?.trim() || !(h > 0) || !(w > 0)) return null;
  return Math.round((w / (h / 100) ** 2) * 10) / 10;
}

/** Field key -> message. Empty when the draft can be submitted. */
export function validateEnrollment(draft: EnrollmentDraft, options: EnrollmentOptions): Record<string, string> {
  const errors: Record<string, string> = {};
  const phone = normalisePhone(draft.phone_e164);

  if (!draft.patient_name.trim()) errors.patient_name = "Enter the patient's name.";
  if (!draft.mrn.trim()) errors.mrn = "Enter the hospital record number.";
  if (!draft.gender) errors.gender = "Choose the patient's sex.";
  if (!PHONE.test(phone)) errors.phone_e164 = "Use international format, e.g. +91 98765 43210.";
  if (draft.date_of_birth && draft.surgery_date && draft.date_of_birth >= draft.surgery_date) {
    errors.date_of_birth = "Date of birth must be before surgery.";
  }

  if (!isBlankPhone(draft.alt_phone_e164)) {
    const alt = normalisePhone(draft.alt_phone_e164);
    if (!PHONE.test(alt)) errors.alt_phone_e164 = "Use international format, e.g. +91 98765 43210.";
    else if (alt === phone) errors.alt_phone_e164 = "Use a different number from the WhatsApp number.";
  }
  if (draft.email.trim() && !EMAIL.test(draft.email.trim())) errors.email = "Enter a valid email address.";

  if (!draft.address_line.trim()) errors.address_line = "Enter the house and street.";
  if (!draft.address_district.trim()) errors.address_district = "Enter the district.";
  if (!POSTAL_CODE.test(draft.address_postal_code.trim())) errors.address_postal_code = "Enter the PIN code.";

  const seen = new Set<string>();
  draft.contacts.forEach((contact, i) => {
    const contactPhone = normalisePhone(contact.phone_e164);
    if (!contact.name.trim()) errors[`contacts.${i}.name`] = "Enter the contact's name.";
    if (!contact.relationship) errors[`contacts.${i}.relationship`] = "Choose how they are related.";
    if (!PHONE.test(contactPhone)) errors[`contacts.${i}.phone_e164`] = "Use international format, e.g. +91 98765 43210.";
    else if (contactPhone === phone) errors[`contacts.${i}.phone_e164`] = "Use someone else's number, not the patient's.";
    else if (seen.has(contactPhone)) errors[`contacts.${i}.phone_e164`] = "Another contact already has this number.";
    seen.add(contactPhone);
  });

  if (!draft.procedure_code) errors.procedure_code = "Choose the procedure.";
  if (!draft.operative_side) errors.operative_side = "Choose which knee was replaced.";
  if (!draft.surgery_date) errors.surgery_date = "Enter the surgery date.";
  if (!draft.discharge_date) errors.discharge_date = "Enter the discharge date.";
  if (draft.surgery_date && draft.discharge_date && draft.discharge_date < draft.surgery_date) {
    errors.discharge_date = "Discharge cannot be before surgery.";
  }
  if (draft.discharge_date > options.today) errors.discharge_date = "Discharge cannot be in the future.";

  for (const param of options.baseline_parameters) {
    const raw = draft.baseline[param.code]?.trim();
    if (!raw || param.type === "ordinal") continue;
    const value = Number(raw);
    if (Number.isNaN(value) || (param.value_min !== null && value < param.value_min) ||
        (param.value_max !== null && value > param.value_max)) {
      errors[`baseline.${param.code}`] = `Between ${param.value_min} and ${param.value_max}.`;
    }
  }
  const systolic = Number(draft.baseline.bp_sys);
  const diastolic = Number(draft.baseline.bp_dia);
  if (draft.baseline.bp_sys?.trim() && draft.baseline.bp_dia?.trim() && !errors["baseline.bp_sys"] &&
      !errors["baseline.bp_dia"] && systolic <= diastolic) {
    errors["baseline.bp_dia"] = "Must be lower than the systolic pressure.";
  }

  if (!draft.consent_version.trim()) errors.consent_version = "Enter the consent form version.";
  if (!draft.consent_confirmed) errors.consent_confirmed = "Confirm the patient has consented to monitoring.";
  if (!draft.data_processing_consent) errors.data_processing_consent = "Monitoring needs consent to process health data.";
  if (!draft.contact_sharing_consent) errors.contact_sharing_consent = "Record the patient's answer.";
  return errors;
}

const FIELD_ORDER = [
  "patient_name", "mrn", "gender", "date_of_birth", "phone_e164", "alt_phone_e164", "email",
  "address_line", "address_district", "address_postal_code", "contacts",
  "procedure_code", "operative_side", "surgery_date", "discharge_date", "baseline",
  "consent_version", "consent_confirmed", "data_processing_consent", "contact_sharing_consent",
];

const FIELD_LABELS: Record<string, string> = {
  patient_name: "Full name",
  mrn: "MRN",
  gender: "Sex",
  date_of_birth: "Date of birth",
  phone_e164: "WhatsApp number",
  alt_phone_e164: "SMS number",
  email: "Email",
  address_line: "House and street",
  address_district: "District",
  address_postal_code: "PIN code",
  procedure_code: "Procedure",
  operative_side: "Operative side",
  surgery_date: "Surgery date",
  discharge_date: "Discharge date",
  consent_version: "Consent form version",
  consent_confirmed: "Monitoring consent",
  data_processing_consent: "Data processing consent",
  contact_sharing_consent: "Sharing with contacts",
};

const CONTACT_FIELD_LABELS: Record<string, string> = { name: "name", relationship: "relationship", phone_e164: "phone" };

/** Errors in the order the fields appear on the form, with a short label for the summary. */
export function describeErrors(
  errors: Record<string, string>,
  options: EnrollmentOptions,
): { key: string; label: string; message: string }[] {
  const rank = (key: string) => {
    const [head, index, field] = key.split(".");
    const base = FIELD_ORDER.indexOf(head) * 1000;
    if (head === "contacts") return base + Number(index) * 10 + Object.keys(CONTACT_FIELD_LABELS).indexOf(field);
    if (head === "baseline") return base + options.baseline_parameters.findIndex((p) => p.code === index);
    return base;
  };
  const label = (key: string) => {
    const [head, index, field] = key.split(".");
    if (head === "contacts") return `Contact ${Number(index) + 1} ${CONTACT_FIELD_LABELS[field]}`;
    if (head === "baseline") return options.baseline_parameters.find((p) => p.code === index)?.name ?? index;
    return FIELD_LABELS[key] ?? key;
  };
  return Object.keys(errors)
    .sort((a, b) => rank(a) - rank(b))
    .map((key) => ({ key, label: label(key), message: errors[key] }));
}

/** DOM id of the control behind an error key, so the summary can jump to it. */
export function fieldId(key: string): string {
  return `enroll-${key.replace(/\./g, "-")}`;
}

/** The API payload: blank optional fields are sent as null and blank baseline fields left out, not sent as zero. */
export function toEnrollmentRequest(draft: EnrollmentDraft, options: EnrollmentOptions): EnrollmentRequest {
  const baseline: Record<string, number | string> = {};
  for (const param of options.baseline_parameters) {
    const raw = draft.baseline[param.code]?.trim();
    if (!raw) continue;
    baseline[param.code] = param.type === "ordinal" ? raw : Number(raw);
  }
  const optional = (value: string) => value.trim() || null;
  return {
    patient_name: draft.patient_name.trim(),
    mrn: draft.mrn.trim(),
    phone_e164: normalisePhone(draft.phone_e164),
    language_code: draft.language_code,
    date_of_birth: draft.date_of_birth || null,
    gender: draft.gender as Gender,
    address: {
      line: draft.address_line.trim(),
      city: optional(draft.address_city),
      district: draft.address_district.trim(),
      state: optional(draft.address_state),
      postal_code: draft.address_postal_code.trim(),
    },
    alt_phone_e164: isBlankPhone(draft.alt_phone_e164) ? null : normalisePhone(draft.alt_phone_e164),
    email: optional(draft.email),
    emergency_contacts: draft.contacts.map((c) => ({
      name: c.name.trim(),
      relationship: c.relationship as Relationship,
      phone_e164: normalisePhone(c.phone_e164),
    })),
    procedure_code: draft.procedure_code,
    operative_side: draft.operative_side as OperativeSide,
    surgery_date: draft.surgery_date,
    discharge_date: draft.discharge_date,
    checkin_window: draft.checkin_window,
    consent_version: draft.consent_version.trim(),
    consent_confirmed: true,
    data_processing_consent: true,
    contact_sharing_consent: draft.contact_sharing_consent === "yes",
    baseline,
  };
}
