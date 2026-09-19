import { describe, expect, it } from "vitest";
import { formatDate, formatPct, formatShortDate } from "@/lib/format";

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
