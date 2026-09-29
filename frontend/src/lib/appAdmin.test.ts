import { describe, expect, it } from "vitest";
import {
  bindingDraft,
  hospitalDraft,
  newBindingDraft,
  parseBinding,
  starterRule,
  suggestVersion,
  toHospitalFields,
  validateHospital,
} from "@/lib/appAdmin";
import type { AvailableParameter, RulesetBinding } from "@/lib/appAdminApi";
import { allowedPath, homePath, isClinicalSession, type Session } from "@/lib/session";

const ZONES = ["Asia/Kolkata", "Europe/London"];

describe("hospital form", () => {
  it("starts a new hospital in India with a 15-minute escalation window", () => {
    const draft = hospitalDraft();
    expect([draft.timezone, draft.ack_window_mins, draft.privacy_law, draft.is_active]).toEqual(["Asia/Kolkata", "15", "DPDP-2023", true]);
  });

  it("needs a code only for a new hospital, a name, a listed time zone and whole minutes", () => {
    const draft = { ...hospitalDraft(), hospital_code: "x", hospital_name: " ", timezone: "Mars/Base", ack_window_mins: "2.5" };
    expect(Object.keys(validateHospital(draft, true, ZONES)).sort()).toEqual(["ack_window_mins", "hospital_code", "hospital_name", "timezone"]);
    expect(validateHospital(draft, false, ZONES).hospital_code).toBeUndefined();
    expect(validateHospital({ ...draft, hospital_code: "cbe-02", hospital_name: "A", timezone: "Europe/London", ack_window_mins: "20" }, true, ZONES)).toEqual({});
  });

  it("sends the window in seconds and a blank city as null", () => {
    const fields = toHospitalFields({ ...hospitalDraft(), hospital_name: " Salem Ortho ", ack_window_mins: "20" });
    expect([fields.hospital_name, fields.city, fields.ack_window_secs]).toEqual(["Salem Ortho", null, 1200]);
  });
});

describe("suggestVersion", () => {
  it("steps the newest minor version and skips names already taken", () => {
    expect(suggestVersion(["1.0.0"])).toBe("1.1.0");
    expect(suggestVersion(["1.0.0", "1.1.0", "0.9.0"])).toBe("1.2.0");
    expect(suggestVersion(["2.0.0", "1.4.0"])).toBe("2.1.0");
    expect(suggestVersion(["1.0.0", "1.2.0", "1.1.0"])).toBe("1.3.0");
    expect(suggestVersion(["beta"])).toBe("1.0.0");
  });
});

const PAIN: RulesetBinding = {
  parameter_code: "pain", parameter_name: "Pain score", parameter_type: "numeric", unit: null,
  display_section: "readings", display_order: 2, collect_from_day: 0, collect_to_day: 84, score_from_day: 0, score_to_day: 84,
  weight: 2, is_mandatory: false, question_text: "How bad is your pain?", nurse_script: null,
  scoring_config: { direction: "higher_is_worse", bands: [[0, 5, 0], [5, 99, 1]] },
  scoring_summary: "≥5 → 1", direction: "higher_is_worse",
};

describe("measure editor", () => {
  it("round-trips an existing measure", () => {
    const parsed = parseBinding(bindingDraft(PAIN), 84);
    expect(parsed.errors).toBeNull();
    expect(parsed.binding).toMatchObject({ display_order: 2, weight: 2, scoring_config: PAIN.scoring_config, nurse_script: null });
  });

  it("refuses windows the patient is not asked in, and broken JSON", () => {
    const draft = { ...bindingDraft(PAIN), collect_from_day: "5", score_from_day: "2", scoring_config: "{bands: [" };
    const { errors } = parseBinding(draft, 84);
    expect(Object.keys(errors ?? {}).sort()).toEqual(["score_from_day", "scoring_config"]);
  });

  it("refuses days beyond the monitoring period and a rule that is not an object", () => {
    const { errors } = parseBinding({ ...bindingDraft(PAIN), collect_to_day: "90", scoring_config: "[1, 2]" }, 84);
    expect(Object.keys(errors ?? {}).sort()).toEqual(["collect_to_day", "scoring_config"]);
  });

  it("starts a new measure with a rule that fits its type", () => {
    const calf: AvailableParameter = { parameter_code: "calf_pain", parameter_name: "Calf pain", parameter_type: "boolean", unit: null, option_codes: [] };
    const knee: AvailableParameter = { parameter_code: "knee_bend", parameter_name: "Knee bend", parameter_type: "ordinal", unit: null, option_codes: ["chair", "car"] };
    expect(starterRule(calf)).toEqual({ binary_score: 1 });
    expect(starterRule(knee)).toEqual({ milestone: { "14": "chair" }, score: 1 });
    const draft = newBindingDraft(calf, 42, 13);
    expect([draft.display_section, draft.display_order, draft.collect_to_day]).toEqual(["checks", "13", "42"]);
  });
});

describe("which way a measure goes wrong", () => {
  const spo2: AvailableParameter = { parameter_code: "spo2", parameter_name: "Oxygen", parameter_type: "numeric", unit: "%", option_codes: [] };

  it("is picked from a list, so it never appears in the JSON the author edits", () => {
    const draft = bindingDraft(PAIN);
    expect(draft.direction).toBe("higher_is_worse");
    expect(draft.scoring_config).not.toContain("direction");
    expect(JSON.parse(draft.scoring_config)).toEqual({ bands: [[0, 5, 0], [5, 99, 1]] });
  });

  it("goes back into the rule on save", () => {
    const { binding } = parseBinding({ ...bindingDraft(PAIN), direction: "higher_is_better" }, 84);
    expect(binding?.scoring_config).toEqual({ direction: "higher_is_better", bands: [[0, 5, 0], [5, 99, 1]] });
  });

  it("is left out for a measure where higher means nothing", () => {
    const calf: AvailableParameter = { parameter_code: "calf_pain", parameter_name: "Calf pain", parameter_type: "boolean", unit: null, option_codes: [] };
    const draft = newBindingDraft(calf, 42, 3);
    expect(draft.direction).toBe("");
    expect(parseBinding({ ...draft, question_text: "Calf sore?" }, 42).binding?.scoring_config).toEqual({ binary_score: 1 });
  });

  it("starts a new numeric measure at higher is worse, and refuses a second copy typed into the JSON", () => {
    const draft = newBindingDraft(spo2, 42, 4);
    expect(draft.direction).toBe("higher_is_worse");
    const typed = { ...draft, question_text: "Oxygen?", scoring_config: '{"direction": "higher_is_better", "bands": [[0, 95, 1]]}' };
    expect(parseBinding(typed, 42).errors?.scoring_config).toContain("list above");
  });
});

const session = (role: string, hospitalId: number | null): Session => ({
  token: "t", expiresAt: Date.now() + 60_000, adminUserId: "u", hospitalId,
  hospitalName: hospitalId === null ? null : "Noyyal Ortho", fullName: "Someone", role,
});

describe("where each role belongs", () => {
  it("sends app admins to the admin area and clinicians to the dashboard", () => {
    expect(homePath(session("app_admin", null))).toBe("/app_admin");
    expect(homePath(session("admin", 1))).toBe("/");
  });

  it("keeps each role out of the other's screens", () => {
    expect(allowedPath(session("app_admin", null), "/app_admin/rulesets")).toBe(true);
    expect(allowedPath(session("app_admin", null), "/patients")).toBe(false);
    expect(allowedPath(session("superadmin", 1), "/app_admin")).toBe(false);
    expect(allowedPath(session("superadmin", 1), "/app_administrator-notes")).toBe(true);
  });

  it("treats only a hospital-bound, non-admin session as clinical", () => {
    expect(isClinicalSession(session("admin", 1))).toBe(true);
    expect(isClinicalSession(session("app_admin", null))).toBe(false);
  });
});
