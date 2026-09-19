import { describe, expect, it } from "vitest";
import { columnPath, linePath, nearestIndex, niceTicks, scaleLinear, stepPath } from "@/lib/chart";

describe("niceTicks", () => {
  it("brackets the data with round steps", () => {
    expect(niceTicks(36.4, 38.9, 5)).toEqual([36, 37, 38, 39]);
    expect(niceTicks(36.4, 37.6, 5)).toEqual([36, 36.5, 37, 37.5, 38]);
    expect(niceTicks(0, 100, 5)).toEqual([0, 25, 50, 75, 100]);
    expect(niceTicks(0, 1180, 5)).toEqual([0, 500, 1000, 1500]);
  });

  it("widens a flat series so it has an axis", () => {
    const ticks = niceTicks(37, 37, 5);
    expect(ticks[0]).toBeLessThan(37);
    expect(ticks[ticks.length - 1]).toBeGreaterThan(37);
  });

  it("survives having no data", () => {
    expect(niceTicks(Infinity, -Infinity)).toEqual([0, 1]);
  });
});

describe("scaleLinear", () => {
  it("maps the domain onto the range, including inverted ranges", () => {
    const y = scaleLinear([0, 100], [200, 0]);
    expect(y(0)).toBe(200);
    expect(y(50)).toBe(100);
    expect(y(100)).toBe(0);
  });
});

describe("linePath", () => {
  it("lifts the pen at missing values instead of bridging them", () => {
    const d = linePath([
      { x: 0, y: 10 },
      { x: 10, y: 20 },
      { x: 20, y: null },
      { x: 30, y: 15 },
      { x: 40, y: 5 },
    ]);
    expect(d).toBe("M0,10L10,20M30,15L40,5");
  });

  it("draws nothing for an empty series", () => {
    expect(linePath([{ x: 0, y: null }])).toBe("");
  });
});

describe("stepPath", () => {
  it("draws a flat run per day and joins changes at slot edges", () => {
    expect(stepPath([{ x: 10, y: 50 }, { x: 20, y: 40 }], 5)).toBe("M5,50L15,50L15,40L25,40");
  });

  it("breaks where there is no threshold", () => {
    expect(stepPath([{ x: 10, y: 50 }, { x: 20, y: null }, { x: 30, y: 50 }], 5)).toBe("M5,50L15,50M25,50L35,50");
  });
});

describe("columnPath", () => {
  it("rounds only the top corners", () => {
    const d = columnPath(0, 10, 20, 30, 4);
    expect(d.startsWith("M0,40V14Q0,10 4,10")).toBe(true);
    expect(d.endsWith("V40Z")).toBe(true);
  });

  it("shrinks the radius for a very short column and skips an empty one", () => {
    expect(columnPath(0, 0, 20, 2, 4)).toContain("Q0,0 2,0");
    expect(columnPath(0, 0, 20, 0)).toBe("");
  });
});

describe("nearestIndex", () => {
  it("snaps the crosshair to the nearest point", () => {
    expect(nearestIndex([0, 10, 20, 30], 14)).toBe(1);
    expect(nearestIndex([0, 10, 20, 30], 99)).toBe(3);
  });
});
