import { describe, expect, it } from "vitest";
import { formatAddress, formatDate, formatPct, formatPhone, formatSexAge, formatShortDate, formatTimeWindow } from "@/lib/format";

describe("calendar dates", () => {
  it("shows the date as written, whatever the viewer's timezone", () => {
    // Parsed as a Date this would be UTC midnight, the day before in the Americas.
    expect(formatDate("2026-09-19")).toBe("19 Sept 2026");
    expect(formatShortDate("2026-01-01")).toBe("1 Jan");
  });

  it("accepts a timestamp and uses its date part", () => {
    expect(formatShortDate("2026-09-19T23:59:00+00:00")).toBe("19 Sept");
  });
});

describe("formatPct", () => {
  it("shows a dash for no data, never a made-up zero", () => {
    expect(formatPct(null)).toBe("—");
    expect(formatPct(0)).toBe("0.0%");
    expect(formatPct(27.27)).toBe("27.3%");
  });
});

describe("formatAddress", () => {
  const home = { line: "12 Race Course Road", city: "Coimbatore", district: "Coimbatore", state: "Tamil Nadu", postal_code: "641018" };

  it("does not repeat a district that is also the city", () => {
    expect(formatAddress(home)).toBe("12 Race Course Road, Coimbatore, Tamil Nadu 641018");
  });

  it("names the district when it differs and skips blank parts", () => {
    expect(formatAddress({ ...home, city: "Avinashi", district: "Tiruppur", state: null })).toBe(
      "12 Race Course Road, Avinashi, Tiruppur 641018",
    );
    expect(formatAddress({ line: null, city: null, district: "Coimbatore", state: null, postal_code: null })).toBe("Coimbatore");
  });
});

describe("formatSexAge", () => {
  it("leaves out what was not recorded", () => {
    expect(formatSexAge("female", 68)).toBe("Female, 68 years");
    expect(formatSexAge("male", null)).toBe("Male");
    expect(formatSexAge("unknown", 70)).toBe("70 years");
    expect(formatSexAge("unknown", null)).toBe("");
  });
});

describe("formatTimeWindow", () => {
  it("drops the seconds", () => {
    expect(formatTimeWindow("08:00:00", "10:00:00")).toBe("08:00–10:00");
  });
});

describe("formatPhone", () => {
  it("spaces an Indian number the way it is read aloud", () => {
    expect(formatPhone("+919862817328")).toBe("+91 98628 17328");
  });

  it("leaves a number it cannot group alone rather than guessing", () => {
    expect(formatPhone("+14155550123")).toBe("+14155550123");
    expect(formatPhone("+9198628")).toBe("+9198628");
  });

  it("has nothing to show for a patient with no number on file", () => {
    expect(formatPhone(null)).toBe("");
    expect(formatPhone(undefined)).toBe("");
  });
});
