import { describe, expect, it } from "vitest";
import type { EnrollmentOptions } from "@/lib/clinicalApi";
import {
  bmi,
  describeErrors,
  emptyDraft,
  fieldId,
  normalisePhone,
  toEnrollmentRequest,
  validateEnrollment,
  type EnrollmentDraft,
} from "@/lib/enrollment";

const OPTIONS: EnrollmentOptions = {
  procedures: [{ procedure_code: "TKR", procedure_name: "Total knee replacement", observation_days: 84, ruleset_version: "1.0.0" }],
  languages: ["en", "ta", "hi"],
  today: "2026-09-19",
  privacy_law: "DPDP-2023",
  checkin_windows: [
    { code: "morning", label: "Morning", start: "08:00:00", end: "10:00:00" },
    { code: "evening", label: "Evening", start: "17:00:00", end: "19:00:00" },
  ],
  baseline_parameters: [
    { code: "bp_sys", name: "Blood pressure, systolic", type: "numeric", unit: "mmHg", value_min: 60, value_max: 260, decimals: 0, options: [] },
    { code: "bp_dia", name: "Blood pressure, diastolic", type: "numeric", unit: "mmHg", value_min: 30, value_max: 160, decimals: 0, options: [] },
    { code: "temp_c", name: "Temperature", type: "numeric", unit: "C", value_min: 30, value_max: 45, decimals: 1, options: [] },
    {
      code: "walk_aid", name: "Walking aid in use", type: "ordinal", unit: null, value_min: null, value_max: null, decimals: 0,
      options: [{ code: "walker", label: "Walking frame", rank: 1 }],
    },
  ],
};

function valid(overrides: Partial<EnrollmentDraft> = {}): EnrollmentDraft {
  return {
    ...emptyDraft(OPTIONS),
    patient_name: "Lakshmi Narayanan",
    mrn: "MRN-1",
    phone_e164: "+919876543210",
    gender: "female",
    address_line: "12 Race Course Road",
    address_district: "Coimbatore",
    address_postal_code: "641018",
    contacts: [{ name: "Arun Narayanan", relationship: "son", phone_e164: "+919812345678" }],
    operative_side: "right",
    surgery_date: "2026-09-15",
    discharge_date: "2026-09-17",
    consent_confirmed: true,
    data_processing_consent: true,
    contact_sharing_consent: "yes",
    ...overrides,
  };
}

describe("validateEnrollment", () => {
  it("starts with discharge today, the only procedure and the first check-in window chosen", () => {
    const draft = emptyDraft(OPTIONS);
    expect(draft.discharge_date).toBe("2026-09-19");
    expect(draft.procedure_code).toBe("TKR");
    expect(draft.checkin_window).toBe("morning");
    expect(draft.contacts).toHaveLength(1);
    // Deliberately not defaulted: which knee it is cannot be guessed, and a
    // pre-selected side is one a hurried clinician would accept unread.
    expect(draft.operative_side).toBe("");
  });

  it("will not enroll a knee replacement without saying which knee", () => {
    expect(validateEnrollment(valid({ operative_side: "" }), OPTIONS)).toEqual({
      operative_side: "Choose which knee was replaced.",
    });
  });

  it("passes a complete draft", () => {
    expect(validateEnrollment(valid(), OPTIONS)).toEqual({});
  });

  it("requires consent and an international phone number", () => {
    const errors = validateEnrollment(valid({ consent_confirmed: false, phone_e164: "9876543210" }), OPTIONS);
    expect(Object.keys(errors).sort()).toEqual(["consent_confirmed", "phone_e164"]);
  });

  it("accepts phone numbers typed with spaces and dashes", () => {
    expect(validateEnrollment(valid({ phone_e164: "+91 98765 43210" }), OPTIONS)).toEqual({});
    expect(validateEnrollment(valid({ phone_e164: "+91-98765-43210" }), OPTIONS)).toEqual({});
  });

  it("requires sex, a home address and the data-processing and sharing answers", () => {
    const errors = validateEnrollment(
      valid({ gender: "", address_line: " ", address_district: "", address_postal_code: "!", data_processing_consent: false, contact_sharing_consent: "" }),
      OPTIONS,
    );
    expect(Object.keys(errors).sort()).toEqual([
      "address_district", "address_line", "address_postal_code", "contact_sharing_consent", "data_processing_consent", "gender",
    ]);
  });

  it("accepts a refusal to share with contacts as an answer", () => {
    expect(validateEnrollment(valid({ contact_sharing_consent: "no" }), OPTIONS)).toEqual({});
  });

  it("needs at least one complete emergency contact on someone else's number", () => {
    const blank = validateEnrollment(valid({ contacts: [{ name: "", relationship: "", phone_e164: "+91" }] }), OPTIONS);
    expect(Object.keys(blank).sort()).toEqual(["contacts.0.name", "contacts.0.phone_e164", "contacts.0.relationship"]);

    const patientsOwn = valid({ contacts: [{ name: "Arun", relationship: "son", phone_e164: "+91 98765 43210" }] });
    expect(validateEnrollment(patientsOwn, OPTIONS)["contacts.0.phone_e164"]).toMatch(/not the patient's/);

    const twice = valid({
      contacts: [
        { name: "Arun", relationship: "son", phone_e164: "+919812345678" },
        { name: "Meera", relationship: "spouse", phone_e164: "+91 98123 45678" },
      ],
    });
    expect(Object.keys(validateEnrollment(twice, OPTIONS))).toEqual(["contacts.1.phone_e164"]);
  });

  it("treats the optional SMS number and email as optional, but checks them when given", () => {
    expect(validateEnrollment(valid({ alt_phone_e164: "+91", email: " " }), OPTIONS)).toEqual({});
    const errors = validateEnrollment(valid({ alt_phone_e164: "+91 98765 43210", email: "not-an-email" }), OPTIONS);
    expect(errors.alt_phone_e164).toMatch(/different number/);
    expect(errors.email).toBeDefined();
  });

  it("rejects impossible dates", () => {
    expect(validateEnrollment(valid({ discharge_date: "2026-09-14" }), OPTIONS).discharge_date).toMatch(/before surgery/);
    expect(validateEnrollment(valid({ discharge_date: "2026-09-20" }), OPTIONS).discharge_date).toMatch(/future/);
    expect(validateEnrollment(valid({ date_of_birth: "2026-09-16" }), OPTIONS).date_of_birth).toBeDefined();
  });

  it("checks baseline readings against the parameter's range", () => {
    expect(validateEnrollment(valid({ baseline: { temp_c: "50" } }), OPTIONS)["baseline.temp_c"]).toBeDefined();
    expect(validateEnrollment(valid({ baseline: { temp_c: "36.9" } }), OPTIONS)).toEqual({});
  });

  it("needs the systolic pressure above the diastolic", () => {
    expect(validateEnrollment(valid({ baseline: { bp_sys: "80", bp_dia: "90" } }), OPTIONS)["baseline.bp_dia"]).toBeDefined();
    expect(validateEnrollment(valid({ baseline: { bp_sys: "132", bp_dia: "84" } }), OPTIONS)).toEqual({});
  });
});

describe("describeErrors", () => {
  it("lists errors in form order with labels a nurse recognises", () => {
    const errors = validateEnrollment(
      valid({ consent_confirmed: false, phone_e164: "123", contacts: [{ name: "", relationship: "son", phone_e164: "+919812345678" }], baseline: { temp_c: "99" } }),
      OPTIONS,
    );
    expect(describeErrors(errors, OPTIONS).map((e) => e.label)).toEqual([
      "WhatsApp number", "Contact 1 name", "Temperature", "Monitoring consent",
    ]);
  });

  it("gives every error key a DOM id without dots", () => {
    expect(fieldId("contacts.1.phone_e164")).toBe("enroll-contacts-1-phone_e164");
  });
});

describe("helpers", () => {
  it("normalises printed phone numbers", () => {
    expect(normalisePhone("+91 (98765) 432-10")).toBe("+919876543210");
  });

  it("works out BMI only when both measures are given", () => {
    expect(bmi("158", "71.4")).toBe(28.6);
    expect(bmi("", "71.4")).toBeNull();
    expect(bmi("158", undefined)).toBeNull();
  });
});

describe("toEnrollmentRequest", () => {
  it("omits blank baseline fields rather than sending zero", () => {
    const body = toEnrollmentRequest(valid({ baseline: { temp_c: " 36.9 ", walk_aid: "walker" } }), OPTIONS);
    expect(body.baseline).toEqual({ temp_c: 36.9, walk_aid: "walker" });
    expect(toEnrollmentRequest(valid({ baseline: { temp_c: "" } }), OPTIONS).baseline).toEqual({});
  });

  it("sends empty optional details as null", () => {
    const body = toEnrollmentRequest(valid({ alt_phone_e164: "+91", email: "" }), OPTIONS);
    expect([body.date_of_birth, body.alt_phone_e164, body.email, body.address.city, body.address.state]).toEqual([
      null, null, null, null, null,
    ]);
  });

  it("sends normalised numbers, the contacts in order and the sharing answer as a boolean", () => {
    const body = toEnrollmentRequest(
      valid({
        phone_e164: "+91 98765 43210",
        contact_sharing_consent: "no",
        contacts: [
          { name: " Arun ", relationship: "son", phone_e164: "+91-98123-45678" },
          { name: "Meera", relationship: "spouse", phone_e164: "+919800000001" },
        ],
      }),
      OPTIONS,
    );
    expect(body.phone_e164).toBe("+919876543210");
    expect(body.emergency_contacts).toEqual([
      { name: "Arun", relationship: "son", phone_e164: "+919812345678" },
      { name: "Meera", relationship: "spouse", phone_e164: "+919800000001" },
    ]);
    expect([body.contact_sharing_consent, body.data_processing_consent]).toEqual([false, true]);
  });
});
