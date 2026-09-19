import { describe, expect, it } from "vitest";
import type { EnrollmentOptions } from "@/lib/clinicalApi";
import { emptyDraft, toEnrollmentRequest, validateEnrollment, type EnrollmentDraft } from "@/lib/enrollment";

const OPTIONS: EnrollmentOptions = {
  procedures: [{ procedure_code: "TKR", procedure_name: "Total knee replacement", observation_days: 84, ruleset_version: "1.0.0" }],
  languages: ["en", "ta", "hi"],
  today: "2026-09-19",
  baseline_parameters: [
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
    surgery_date: "2026-09-15",
    discharge_date: "2026-09-17",
    consent_confirmed: true,
    ...overrides,
  };
}

describe("validateEnrollment", () => {
  it("starts with discharge today and the only procedure chosen", () => {
    const draft = emptyDraft(OPTIONS);
    expect(draft.discharge_date).toBe("2026-09-19");
    expect(draft.procedure_code).toBe("TKR");
  });

  it("passes a complete draft", () => {
    expect(validateEnrollment(valid(), OPTIONS)).toEqual({});
  });

  it("requires consent and an international phone number", () => {
    const errors = validateEnrollment(valid({ consent_confirmed: false, phone_e164: "9876543210" }), OPTIONS);
    expect(Object.keys(errors).sort()).toEqual(["consent_confirmed", "phone_e164"]);
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
});

describe("toEnrollmentRequest", () => {
  it("omits blank baseline fields rather than sending zero", () => {
    const body = toEnrollmentRequest(valid({ baseline: { temp_c: " 36.9 ", walk_aid: "walker" } }), OPTIONS);
    expect(body.baseline).toEqual({ temp_c: 36.9, walk_aid: "walker" });
    expect(toEnrollmentRequest(valid({ baseline: { temp_c: "" } }), OPTIONS).baseline).toEqual({});
  });

  it("sends an empty date of birth as null", () => {
    expect(toEnrollmentRequest(valid(), OPTIONS).date_of_birth).toBeNull();
  });
});
