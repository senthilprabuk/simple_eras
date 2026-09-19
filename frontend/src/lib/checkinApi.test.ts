import { describe, expect, it } from "vitest";
import { FormParameter, FormSection, anchorFor, formatAnswer, stepFor, urgentAnswers } from "@/lib/checkinApi";

function param(overrides: Partial<FormParameter>): FormParameter {
  return {
    parameter_id: 1, code: "x", name: "X", question_text: "X?", type: "numeric", section: "readings",
    unit: null, value_min: 0, value_max: 10, decimals: 0, is_mandatory: false, is_emergency: false,
    is_scored_today: true, options: [], ...overrides,
  };
}

describe("formatAnswer", () => {
  it("never presents an unanswered question as a value", () => {
    expect(formatAnswer(param({}), null)).toBe("Not answered");
  });

  it("formats each type", () => {
    expect(formatAnswer(param({ unit: "bpm" }), 72)).toBe("72 bpm");
    expect(formatAnswer(param({ decimals: 1, unit: "°C" }), 37)).toBe("37.0 °C");
    expect(formatAnswer(param({ type: "boolean" }), false)).toBe("No");
    const ordinal = param({ type: "ordinal", options: [{ code: "cane", label: "Walking stick", rank: 3 }] });
    expect(formatAnswer(ordinal, "cane")).toBe("Walking stick");
  });
});

describe("stepper behaviour", () => {
  it("starts temperature near normal rather than at the range minimum", () => {
    expect(anchorFor(param({ code: "temp_c", value_min: 30, value_max: 45 }))).toBe(36.8);
  });

  it("falls back to the middle of the range", () => {
    expect(anchorFor(param({ code: "unknown", value_min: 0, value_max: 10 }))).toBe(5);
  });

  it("steps by a tenth for one-decimal values", () => {
    expect(stepFor(param({ decimals: 1 }))).toBe(0.1);
    expect(stepFor(param({ code: "steps" }))).toBe(50);
  });
});

describe("urgentAnswers", () => {
  const sections: FormSection[] = [{
    key: "checks",
    parameters: [
      param({ code: "breathless", type: "boolean", is_emergency: true }),
      param({ code: "calf_pain", type: "boolean", is_emergency: false }),
    ],
  }];

  it("flags a yes to an emergency question", () => {
    expect(urgentAnswers(sections, { breathless: true }).map((p) => p.code)).toEqual(["breathless"]);
  });

  it("follows the ruleset's emergency flag, not a hardcoded list", () => {
    expect(urgentAnswers(sections, { calf_pain: true })).toEqual([]);
  });

  it("ignores no and unanswered", () => {
    expect(urgentAnswers(sections, { breathless: false })).toEqual([]);
    expect(urgentAnswers(sections, {})).toEqual([]);
  });
});
