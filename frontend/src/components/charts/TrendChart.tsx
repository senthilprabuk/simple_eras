"use client";

import React, { useId, useMemo, useRef, useState } from "react";
import { linePath, nearestIndex, niceTicks, scaleLinear, stepPath } from "@/lib/chart";
import ChartTable from "@/components/charts/ChartTable";

export interface TrendDatum {
  key: string;
  label: string;
  shortLabel: string;
  value: number | null;
  threshold?: number | null;
}

interface TrendChartProps {
  data: TrendDatum[];
  format: (value: number) => string;
  /** Which side of the threshold is worrying; points past it are marked. */
  thresholdDirection?: "above" | "below" | null;
  domain?: [number, number];
  emptyLabel?: string;
  ariaLabel: string;
  tableCaption: string;
  valueHeader: string;
}

const W = 600;
const H = 210;
const M = { top: 12, right: 18, bottom: 26, left: 46 };
const PRIMARY = "#00647f";
const ALERT = "#ba1a1a";
const GRID = "#e3eaec";
const INK_MUTED = "#3f484d";
const THRESHOLD = "#6f787e";

/**
 * One series over time. Missing values break the line, a stepped dashed line
 * marks the ruleset's scoring threshold, and a crosshair (pointer or arrow
 * keys) reads out the day.
 */
export default function TrendChart({
  data,
  format,
  thresholdDirection = null,
  domain,
  emptyLabel = "No readings yet",
  ariaLabel,
  tableCaption,
  valueHeader,
}: TrendChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [active, setActive] = useState<number | null>(null);
  const titleId = useId();

  const geometry = useMemo(() => {
    const numbers = data.flatMap((d) => [d.value, d.threshold ?? null]).filter((v): v is number => v !== null);
    const ticks = domain ? niceTicks(domain[0], domain[1], 5) : niceTicks(Math.min(...numbers), Math.max(...numbers), 5);
    const y = scaleLinear([ticks[0], ticks[ticks.length - 1]], [H - M.bottom, M.top]);
    const x = data.length > 1
      ? scaleLinear([0, data.length - 1], [M.left, W - M.right])
      : () => (M.left + W - M.right) / 2;
    const xs = data.map((_, i) => x(i));
    const halfSlot = data.length > 1 ? (xs[1] - xs[0]) / 2 : 8;
    const labelEvery = Math.max(1, Math.ceil(data.length / 8));
    return { ticks, y, xs, halfSlot, labelEvery };
  }, [data, domain]);

  const hasValues = data.some((d) => d.value !== null);
  const { ticks, y, xs, halfSlot, labelEvery } = geometry;

  const beyond = (d: TrendDatum) =>
    d.value !== null && d.threshold != null && thresholdDirection !== null &&
    (thresholdDirection === "above" ? d.value > d.threshold : d.value < d.threshold);

  const lastThreshold = [...data].reverse().find((d) => d.threshold != null);

  const moveTo = (clientX: number) => {
    const box = svgRef.current?.getBoundingClientRect();
    if (!box) return;
    setActive(nearestIndex(xs, ((clientX - box.left) / box.width) * W));
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    const last = data.length - 1;
    const next =
      e.key === "ArrowRight" ? Math.min(last, (active ?? -1) + 1)
      : e.key === "ArrowLeft" ? Math.max(0, (active ?? last + 1) - 1)
      : e.key === "Home" ? 0
      : e.key === "End" ? last
      : null;
    if (next !== null) {
      e.preventDefault();
      setActive(next);
    }
  };

  const point = active !== null ? data[active] : null;
  const leftPct = active !== null ? (xs[active] / W) * 100 : 0;

  return (
    <div>
      <div className="relative">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="w-full h-auto overflow-visible focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
          role="img"
          aria-labelledby={titleId}
          tabIndex={0}
          onKeyDown={onKeyDown}
          onFocus={() => setActive((a) => a ?? data.length - 1)}
          onBlur={() => setActive(null)}
          onPointerMove={(e) => moveTo(e.clientX)}
          onPointerLeave={() => setActive(null)}
        >
          <title id={titleId}>{ariaLabel}</title>

          {ticks.map((t) => (
            <g key={t}>
              <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke={GRID} strokeWidth={1} />
              <text x={M.left - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill={INK_MUTED} className="tabular-nums">
                {format(t)}
              </text>
            </g>
          ))}

          {data.map((d, i) =>
            i % labelEvery === 0 || i === data.length - 1 ? (
              <text key={d.key} x={xs[i]} y={H - 6} textAnchor="middle" fontSize={11} fill={INK_MUTED}>
                {d.shortLabel}
              </text>
            ) : null,
          )}

          {thresholdDirection && (
            <path
              d={stepPath(data.map((d, i) => ({ x: xs[i], y: d.threshold != null ? y(d.threshold) : null })), halfSlot)}
              fill="none"
              stroke={THRESHOLD}
              strokeWidth={1.5}
              strokeDasharray="5 4"
            />
          )}
          {thresholdDirection && lastThreshold && (
            <text
              x={W - M.right}
              y={y(lastThreshold.threshold as number) + (thresholdDirection === "above" ? -6 : 13)}
              textAnchor="end"
              fontSize={10}
              fill={INK_MUTED}
            >
              Scoring threshold
            </text>
          )}

          <path
            d={linePath(data.map((d, i) => ({ x: xs[i], y: d.value !== null ? y(d.value) : null })))}
            fill="none"
            stroke={PRIMARY}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {data.map((d, i) =>
            d.value !== null ? (
              <circle
                key={d.key}
                cx={xs[i]}
                cy={y(d.value)}
                r={active === i ? 6 : 4}
                fill={beyond(d) ? ALERT : PRIMARY}
                stroke="#ffffff"
                strokeWidth={2}
              />
            ) : null,
          )}

          {active !== null && (
            <line
              x1={xs[active]}
              x2={xs[active]}
              y1={M.top}
              y2={H - M.bottom}
              stroke={INK_MUTED}
              strokeWidth={1}
              pointerEvents="none"
            />
          )}

          {!hasValues && (
            <text x={W / 2} y={H / 2} textAnchor="middle" fontSize={13} fill={INK_MUTED}>
              {emptyLabel}
            </text>
          )}
        </svg>

        {point && (
          <div
            role="status"
            className="absolute top-0 pointer-events-none z-10 px-2.5 py-1.5 rounded-lg bg-inverse-surface text-inverse-on-surface shadow-lg whitespace-nowrap"
            style={{
              left: `${leftPct}%`,
              transform: `translateX(${leftPct < 15 ? "0" : leftPct > 85 ? "-100%" : "-50%"})`,
            }}
          >
            <div className="font-title-sm">{point.value !== null ? format(point.value) : "No reading"}</div>
            <div className="font-body-sm opacity-80">{point.label}</div>
            {point.threshold != null && (
              <div className="font-body-sm opacity-80">
                {beyond(point) ? "Past" : "Threshold"} {format(point.threshold)}
              </div>
            )}
          </div>
        )}
      </div>

      <ChartTable
        caption={tableCaption}
        headers={thresholdDirection ? ["Day", valueHeader, "Scoring threshold"] : ["Day", valueHeader]}
        rows={data.map((d) => {
          const row = [d.label, d.value !== null ? format(d.value) : "—"];
          return thresholdDirection ? [...row, d.threshold != null ? format(d.threshold) : "—"] : row;
        })}
      />
    </div>
  );
}
