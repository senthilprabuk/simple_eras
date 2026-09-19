"use client";

import React from "react";
import Link from "next/link";
import type { QueueRow, Tier } from "@/lib/api";
import { currentAgeSecs, formatDuration, reasonText, slaFor, slaLabel } from "@/lib/triage";

interface RiskQueueTableProps {
  rows: QueueRow[];
  emptyMessage: string;
  now: number;
  fetchedAt: number;
  pending: Record<string, boolean>;
  rowErrors: Record<string, string>;
  onAcknowledge: (row: QueueRow) => void;
  onOpen: (row: QueueRow) => void;
}

const TIER_BADGE: Record<Tier, { icon: string; label: string; className: string }> = {
  emergency: { icon: "e911_emergency", label: "EMERGENCY", className: "bg-error text-on-error" },
  critical: {
    icon: "crisis_alert",
    label: "CRITICAL",
    className: "bg-surface-container-lowest border border-error text-error",
  },
  review: { icon: "search", label: "REVIEW", className: "bg-tertiary-fixed text-on-tertiary-fixed" },
  missed: {
    icon: "schedule",
    label: "MISSED",
    className: "bg-surface-bright border border-outline-variant/50 text-on-surface-variant",
  },
};

export function TierBadge({ tier }: { tier: Tier }) {
  const badge = TIER_BADGE[tier];
  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded font-label-sm font-semibold tracking-wide ${badge.className}`}
    >
      <span className="material-symbols-outlined text-[14px]" aria-hidden="true">
        {badge.icon}
      </span>
      {badge.label}
    </span>
  );
}

export default function RiskQueueTable({
  rows,
  emptyMessage,
  now,
  fetchedAt,
  pending,
  rowErrors,
  onAcknowledge,
  onOpen,
}: RiskQueueTableProps) {
  return (
    <section
      aria-label="Risk queue"
      className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 overflow-hidden shadow-sm"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[980px]">
          <thead>
            <tr className="bg-surface-bright/70 border-b border-outline-variant/30 text-on-surface-variant font-label-sm uppercase tracking-wider">
              <th scope="col" className="py-3 px-space-md w-[140px]">Tier</th>
              <th scope="col" className="py-3 px-space-md w-[240px]">Patient</th>
              <th scope="col" className="py-3 px-space-md">Clinical reasons</th>
              <th scope="col" className="py-3 px-space-md w-[170px]">Age / SLA</th>
              <th scope="col" className="py-3 px-space-md w-[230px]">Action</th>
              <th scope="col" className="py-3 px-space-md w-[60px]"><span className="sr-only">Details</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/30">
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="py-space-xl px-space-md text-center font-body-md text-on-surface-variant">
                  {emptyMessage}
                </td>
              </tr>
            )}

            {rows.map((row) => {
              const age = currentAgeSecs(row, fetchedAt, now);
              const sla = slaFor(age, row.ack_window_secs, row.acknowledged);
              const busy = !!pending[row.alert_id];
              const error = rowErrors[row.alert_id];

              return (
                <tr key={row.alert_id} className="hover:bg-surface-bright/60 transition-colors align-middle">
                  <td className="py-3.5 px-space-md">
                    <TierBadge tier={row.tier} />
                  </td>

                  <td className="py-3.5 px-space-md">
                    <Link
                      href={`/patients/${row.episode_id}`}
                      className="font-title-sm text-on-surface hover:text-primary hover:underline"
                    >
                      {row.patient_name}
                    </Link>
                    <div className="font-body-sm text-on-surface-variant">
                      MRN {row.mrn ?? "not recorded"} · {row.procedure_code} · raised on POD {row.day_after_discharge}
                    </div>
                  </td>

                  <td className="py-3.5 px-space-md">
                    <div className="flex flex-wrap gap-1.5">
                      {row.reasons.map((reason, i) => (
                        <span
                          key={i}
                          className="inline-flex items-center px-2 py-0.5 rounded bg-surface-bright border border-outline-variant/40 font-body-sm text-on-surface"
                        >
                          {reasonText(reason)}
                        </span>
                      ))}
                    </div>
                  </td>

                  <td className="py-3.5 px-space-md">
                    <div className="font-title-sm text-on-surface">{formatDuration(age)} ago</div>
                    <div
                      className={`font-label-sm ${
                        sla.state === "breached" ? "text-error font-semibold" : "text-on-surface-variant"
                      }`}
                    >
                      {slaLabel(sla)}
                    </div>
                  </td>

                  <td className="py-3.5 px-space-md">
                    {row.acknowledged ? (
                      <div className="flex flex-col items-start gap-1">
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-bright border border-outline-variant/30 font-label-sm text-on-surface-variant">
                          <span className="material-symbols-outlined text-[15px] text-primary" aria-hidden="true">
                            verified
                          </span>
                          Ack by {row.acknowledged_by_name ?? "a former clinician"}
                        </span>
                        <button
                          type="button"
                          onClick={() => onOpen(row)}
                          className="font-label-md text-primary hover:underline cursor-pointer"
                        >
                          Record outcome
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => onAcknowledge(row)}
                        aria-label={`Acknowledge alert for ${row.patient_name}`}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-primary text-primary font-label-md rounded hover:bg-surface-container-low transition-colors cursor-pointer disabled:opacity-60"
                      >
                        <span
                          className={`material-symbols-outlined text-[16px] ${busy ? "animate-spin" : ""}`}
                          aria-hidden="true"
                        >
                          {busy ? "progress_activity" : "check_circle"}
                        </span>
                        {busy ? "Acknowledging…" : "Acknowledge"}
                      </button>
                    )}
                    {error && (
                      <p role="alert" className="mt-1 font-body-sm text-error">
                        {error}
                      </p>
                    )}
                  </td>

                  <td className="py-3.5 px-space-md text-right">
                    <button
                      type="button"
                      onClick={() => onOpen(row)}
                      aria-label={`Open details for ${row.patient_name}`}
                      className="p-1 rounded text-on-surface-variant hover:text-primary hover:bg-surface-container-low transition-colors cursor-pointer"
                    >
                      <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
                        chevron_right
                      </span>
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
