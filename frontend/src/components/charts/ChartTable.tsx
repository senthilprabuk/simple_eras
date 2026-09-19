import React from "react";

/** The table twin every chart carries, so no value is reachable only by hovering. */
export default function ChartTable({ caption, headers, rows }: { caption: string; headers: string[]; rows: string[][] }) {
  return (
    <details className="mt-space-sm group">
      <summary className="font-label-md text-primary cursor-pointer select-none w-fit">
        <span className="group-open:hidden">Show data table</span>
        <span className="hidden group-open:inline">Hide data table</span>
      </summary>
      <div className="mt-space-sm max-h-64 overflow-auto border border-outline-variant/30 rounded-lg">
        <table className="w-full text-left font-body-sm tabular-nums">
          <caption className="sr-only">{caption}</caption>
          <thead className="sticky top-0 bg-surface-container-lowest">
            <tr className="border-b border-outline-variant/30 text-on-surface-variant">
              {headers.map((h) => (
                <th key={h} scope="col" className="px-3 py-1.5 font-semibold">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/20">
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} className="px-3 py-1 text-on-surface">{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
