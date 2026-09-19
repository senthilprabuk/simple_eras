import React from "react";

/**
 * Horizontal bars for one series across nominal categories: every bar the same
 * color (the length carries the value), value at the tip, so no hover or table
 * is needed to read it.
 */
export default function BarList({ items, unit }: { items: { label: string; value: number }[]; unit: string }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="flex flex-col gap-space-sm" aria-label={`Counts of ${unit}`}>
      {items.map((item) => (
        <li key={item.label} className="grid grid-cols-[minmax(9rem,14rem)_1fr] items-center gap-space-sm">
          <span className="font-body-sm text-on-surface truncate">{item.label}</span>
          <span className="flex items-center gap-2">
            {item.value > 0 && (
              <span
                className="h-3 rounded-r bg-primary"
                style={{ width: `${(item.value / max) * 100}%`, maxWidth: "calc(100% - 3rem)" }}
                aria-hidden="true"
              />
            )}
            <span className="font-body-sm text-on-surface tabular-nums">{item.value}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
