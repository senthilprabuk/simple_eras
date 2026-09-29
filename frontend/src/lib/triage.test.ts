import { describe, expect, it } from "vitest";
import type { ParameterReading } from "@/lib/api";
import {
  currentAgeSecs,
  domainOf,
  formatDuration,
  formatReading,
  groupReasons,
  initials,
  isConcerning,
  matchesSearch,
  quietCohort,
  reasonText,
  slaFor,
  slaLabel,
  tierCounts,
} from "@/lib/triage";

describe("currentAgeSecs", () => {
  it("advances the server's age by time elapsed since the fetch", () => {
    expect(currentAgeSecs({ age_secs: 100 }, 1_000_000, 1_030_000)).toBe(130);
  });

  it("never runs backwards if the clock is behind the fetch time", () => {
    expect(currentAgeSecs({ age_secs: 100 }, 1_000_000, 990_000)).toBe(100);
  });
});

describe("formatDuration", () => {
  it.each([
    [30, "under 1m"],
    [60, "1m"],
    [14 * 60 + 59, "14m"],
    [3600, "1h"],
    [3600 + 25 * 60, "1h 25m"],
    [86400, "1d"],
    [86400 + 3 * 3600, "1d 3h"],
  ])("%i seconds -> %s", (secs, text) => {
    expect(formatDuration(secs)).toBe(text);
  });
});

describe("slaFor", () => {
  it("counts down inside the window", () => {
    expect(slaFor(600, 900, false)).toEqual({ state: "due", remainingSecs: 300 });
  });

  it("is breached once the window has passed", () => {
    expect(slaFor(1000, 900, false)).toEqual({ state: "breached", overdueSecs: 100 });
  });

  it("is breached exactly at the deadline, not after", () => {
    expect(slaFor(900, 900, false).state).toBe("breached");
  });

  it("uses each hospital's own window", () => {
    expect(slaFor(1200, 3600, false).state).toBe("due");
  });

  it("stops counting once acknowledged", () => {
    expect(slaFor(99999, 900, true)).toEqual({ state: "acknowledged" });
  });

  it("labels each state in words", () => {
    expect(slaLabel({ state: "due", remainingSecs: 300 })).toBe("5m to acknowledge");
    expect(slaLabel({ state: "breached", overdueSecs: 120 })).toBe("SLA breached 2m ago");
  });
});

describe("queue helpers", () => {
  it("prefers the clinical detail and falls back to a readable name", () => {
    expect(reasonText({ name: "calf_pain", detail: "Calf swelling" })).toBe("Calf swelling");
    expect(reasonText({ name: "calf_pain", detail: null })).toBe("calf pain");
  });

  it("counts every tier, including ones with no alerts", () => {
    expect(tierCounts([{ tier: "critical" }, { tier: "critical" }, { tier: "missed" }])).toEqual({
      emergency: 0,
      critical: 2,
      review: 0,
      missed: 1,
    });
  });

  it("searches name and MRN case-insensitively", () => {
    const row = { patient_name: "Fixture Sudden Clot", mrn: "FX-03" };
    expect(matchesSearch(row, "sudden")).toBe(true);
    expect(matchesSearch(row, "fx-03")).toBe(true);
    expect(matchesSearch(row, "  ")).toBe(true);
    expect(matchesSearch(row, "breathless")).toBe(false);
    expect(matchesSearch({ patient_name: "No Record", mrn: null }, "fx")).toBe(false);
  });

  it("derives the quiet cohort and never goes negative", () => {
    expect(quietCohort({ active_patients: 12, patients_with_open_alerts: 6 })).toBe(6);
    expect(quietCohort({ active_patients: 1, patients_with_open_alerts: 2 })).toBe(0);
  });

  it("makes initials without honorifics", () => {
    expect(initials("Anitha Joseph")).toBe("AJ");
    expect(initials("Dr. Arun Prakash")).toBe("AP");
    expect(initials("")).toBe("?");
  });
});

describe("readings", () => {
  const temp: ParameterReading = {
    code: "temp_c", name: "Temperature", type: "numeric", unit: "C", decimals: 1,
    concerning_when_true: null, baseline: 36.8, current: 38.25,
  };
  const calf: ParameterReading = {
    code: "calf_pain", name: "Calf pain or swelling", type: "boolean", unit: null, decimals: 0,
    concerning_when_true: true, baseline: null, current: true,
  };

  it("formats values with their unit and precision", () => {
    expect(formatReading(temp, temp.current)).toBe("38.3 °C");
    expect(formatReading(calf, calf.current)).toBe("Yes");
    expect(formatReading(calf, calf.baseline)).toBe("—");
  });

  it("flags only the worrying yes/no answer", () => {
    expect(isConcerning(calf)).toBe(true);
    expect(isConcerning({ ...calf, current: false })).toBe(false);
    expect(isConcerning({ ...calf, current: null })).toBe(false);
    expect(isConcerning(temp)).toBe(false);
  });
});

describe("knee recovery domains", () => {
  const reason = (name: string) => ({ name, detail: name.replace(/_/g, " ") });

  it("files each signal under the complication it points at", () => {
    expect(domainOf(reason("calf_pain"))).toBe("dvt");
    expect(domainOf(reason("breathless"))).toBe("dvt");
    expect(domainOf(reason("drainage"))).toBe("infection");
    expect(domainOf(reason("fever_returned"))).toBe("infection");
    expect(domainOf(reason("mobility_regression"))).toBe("mobility");
    expect(domainOf(reason("missed_check_in"))).toBe("missed");
  });

  it("leaves a sign of everything ungrouped rather than claiming a domain", () => {
    // Pain and a raised pulse point at sepsis and at a clot equally, so filing
    // either under one heading would say more than the reading supports.
    expect(domainOf(reason("pain"))).toBe("other");
    expect(domainOf(reason("hr"))).toBe("other");
  });

  it("puts an unknown signal in other rather than dropping it", () => {
    expect(domainOf(reason("something_added_later"))).toBe("other");
  });

  it("groups most time-critical first and keeps every reason", () => {
    const reasons = [reason("drainage"), reason("pain"), reason("calf_pain"), reason("chills")];
    const groups = groupReasons(reasons);

    expect(groups.map((g) => g.domain)).toEqual(["dvt", "infection", "other"]);
    expect(groups.flatMap((g) => g.reasons)).toHaveLength(reasons.length);
    expect(groups[1].reasons.map((r) => r.name)).toEqual(["drainage", "chills"]);
  });

  it("skips a domain with nothing in it", () => {
    expect(groupReasons([reason("calf_pain")]).map((g) => g.domain)).toEqual(["dvt"]);
    expect(groupReasons([])).toEqual([]);
  });
});
