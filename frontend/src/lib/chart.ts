/** Geometry for the hand-built SVG charts. Pure, so it is unit tested. */

export interface PlotPoint {
  x: number;
  y: number | null;
}

const r = (n: number) => Math.round(n * 10) / 10;

/** Round tick values that bracket [min, max], about `count` of them. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  if (min === max) {
    const pad = Math.abs(min) * 0.1 || 1;
    min -= pad;
    max += pad;
  }
  const rawStep = (max - min) / Math.max(1, count - 1);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10) * magnitude;
  const ticks: number[] = [];
  for (let v = Math.floor(min / step) * step; v <= Math.ceil(max / step) * step + step / 2; v += step) {
    ticks.push(Number(v.toFixed(10)));
  }
  return ticks;
}

/** Linear map from a data domain to a pixel range. */
export function scaleLinear(domain: [number, number], range: [number, number]): (v: number) => number {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (v: number) => r0 + (v - d0) * k;
}

/**
 * Line through the points, lifted wherever a value is missing so a day with no
 * check-in shows as a gap instead of being bridged by an invented slope.
 */
export function linePath(points: PlotPoint[]): string {
  let d = "";
  let drawing = false;
  for (const p of points) {
    if (p.y === null) {
      drawing = false;
      continue;
    }
    d += `${drawing ? "L" : "M"}${r(p.x)},${r(p.y)}`;
    drawing = true;
  }
  return d;
}

/**
 * Stepped line for a threshold that changes by day: a flat run across each
 * day's slot, joined at the slot edges, lifted where there is no threshold.
 */
export function stepPath(points: PlotPoint[], halfSlot: number): string {
  let d = "";
  let previous: number | null = null;
  for (const p of points) {
    if (p.y === null) {
      previous = null;
      continue;
    }
    const left = r(p.x - halfSlot);
    const right = r(p.x + halfSlot);
    d += previous === null ? `M${left},${r(p.y)}` : `L${left},${r(p.y)}`;
    d += `L${right},${r(p.y)}`;
    previous = p.y;
  }
  return d;
}

/** Column with a 4px rounded data end and a square base on the baseline. */
export function columnPath(x: number, y: number, width: number, height: number, radius = 4): string {
  if (height <= 0) return "";
  const rr = Math.min(radius, height, width / 2);
  return [
    `M${r(x)},${r(y + height)}`,
    `V${r(y + rr)}`,
    `Q${r(x)},${r(y)} ${r(x + rr)},${r(y)}`,
    `H${r(x + width - rr)}`,
    `Q${r(x + width)},${r(y)} ${r(x + width)},${r(y + rr)}`,
    `V${r(y + height)}`,
    "Z",
  ].join("");
}

/** Index of the point whose x is nearest the pointer, for the crosshair. */
export function nearestIndex(xs: number[], pointerX: number): number {
  let best = 0;
  for (let i = 1; i < xs.length; i++) {
    if (Math.abs(xs[i] - pointerX) < Math.abs(xs[best] - pointerX)) best = i;
  }
  return best;
}
