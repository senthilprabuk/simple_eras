"use client";

import React, { useId, useState } from "react";
import { columnPath, niceTicks, scaleLinear } from "@/lib/chart";
import ChartTable from "@/components/charts/ChartTable";

export interface StackSeries {
  key: string;
  label: string;
  color: string;
}

export interface StackRow {
  key: string;
  label: string;
  values: Record<string, number>;
}

const W = 600;
const H = 220;
const M = { top: 12, right: 12, bottom: 26, left: 40 };
const GAP = 2;
const GRID = "#e3eaec";
const INK_MUTED = "#3f484d";

/**
 * Columns stacked bottom-up in series order, 2px surface gaps between
 * segments, a 4px rounded cap on the top segment only. Hovering or focusing a
 * column reads out every series for it.
 */
export default function StackedColumnChart({
  series,
  rows,
  ariaLabel,
  tableCaption,
}: {
  series: StackSeries[];
  rows: StackRow[];
  ariaLabel: string;
  tableCaption: string;
}) {
  const [active, setActive] = useState<number | null>(null);
  const titleId = useId();

  const totals = rows.map((row) => series.reduce((sum, s) => sum + (row.values[s.key] ?? 0), 0));
  const rawTicks = niceTicks(0, Math.max(4, ...totals), 5);
  const ticks = rawTicks.filter((t) => Number.isInteger(t));
  const top = rawTicks[rawTicks.length - 1];
  const y = scaleLinear([0, top], [H - M.bottom, M.top]);
  const band = (W - M.left - M.right) / Math.max(1, rows.length);
  const width = Math.min(24, band * 0.6);
  const labelEvery = Math.max(1, Math.ceil(rows.length / 8));

  const point = active !== null ? rows[active] : null;
  const centre = (i: number) => M.left + band * i + band / 2;

  return (
    <div>
      <ul className="flex flex-wrap gap-x-space-md gap-y-1 mb-space-sm" aria-label="Legend">
        {series.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5 font-body-sm text-on-surface">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: s.color }} aria-hidden="true" />
            {s.label}
          </li>
        ))}
      </ul>

      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto overflow-visible" role="img" aria-labelledby={titleId}>
          <title id={titleId}>{ariaLabel}</title>

          {ticks.map((t) => (
            <g key={t}>
              <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke={GRID} strokeWidth={1} />
              <text x={M.left - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill={INK_MUTED} className="tabular-nums">
                {t}
              </text>
            </g>
          ))}

          {rows.map((row, i) => {
            const x = centre(i) - width / 2;
            const stacked = series.filter((s) => (row.values[s.key] ?? 0) > 0);
            let base = 0;
            return (
              <g
                key={row.key}
                tabIndex={0}
                role="button"
                aria-label={`${row.label}: ${totals[i]} in total`}
                onPointerEnter={() => setActive(i)}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
                opacity={active === null || active === i ? 1 : 0.55}
                className="focus:outline-none"
              >
                <rect x={centre(i) - band / 2} y={M.top} width={band} height={H - M.top - M.bottom} fill="transparent" />
                {stacked.map((s, j) => {
                  const value = row.values[s.key];
                  const bottomPx = y(base);
                  const topPx = y(base + value);
                  base += value;
                  const isTop = j === stacked.length - 1;
                  const segTop = topPx + (isTop ? 0 : GAP / 2);
                  const segBottom = bottomPx - (j === 0 ? 0 : GAP / 2);
                  const height = Math.max(0, segBottom - segTop);
                  return isTop ? (
                    <path key={s.key} d={columnPath(x, segTop, width, height)} fill={s.color} />
                  ) : (
                    <rect key={s.key} x={x} y={segTop} width={width} height={height} fill={s.color} />
                  );
                })}
              </g>
            );
          })}

          {rows.map((row, i) =>
            i % labelEvery === 0 || i === rows.length - 1 ? (
              <text key={row.key} x={centre(i)} y={H - 6} textAnchor="middle" fontSize={11} fill={INK_MUTED}>
                {row.label}
              </text>
            ) : null,
          )}
        </svg>

        {point && active !== null && (
          <div
            role="status"
            className="absolute top-0 pointer-events-none z-10 px-2.5 py-1.5 rounded-lg bg-inverse-surface text-inverse-on-surface shadow-lg whitespace-nowrap"
            style={{
              left: `${(centre(active) / W) * 100}%`,
              transform: `translateX(${active < rows.length * 0.2 ? "0" : active > rows.length * 0.8 ? "-100%" : "-50%"})`,
            }}
          >
            <div className="font-body-sm opacity-80 mb-0.5">Week of {point.label}</div>
            {series.map((s) => (
              <div key={s.key} className="flex items-center gap-2 font-body-sm">
                <span className="inline-block w-3 h-0.5" style={{ background: s.color }} aria-hidden="true" />
                <span className="font-semibold tabular-nums">{point.values[s.key] ?? 0}</span>
                <span className="opacity-80">{s.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <ChartTable
        caption={tableCaption}
        headers={["Week", ...series.map((s) => s.label), "Total"]}
        rows={rows.map((row, i) => [row.label, ...series.map((s) => String(row.values[s.key] ?? 0)), String(totals[i])])}
      />
    </div>
  );
}
