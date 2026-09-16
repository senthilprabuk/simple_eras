import React from "react";
import { KpiResponse } from "@/lib/api";

interface KpiMetricsProps {
  kpis?: KpiResponse | null;
}

export default function KpiMetrics({ kpis }: KpiMetricsProps) {
  const activePatients = kpis ? kpis.active_patients : 13;
  const openAlerts = kpis ? kpis.open_alerts : 7;
  const ackRate = kpis ? `${kpis.ack_rate_15min.toFixed(1)}%` : "94.2%";
  const missedCheckins = kpis ? kpis.missed_checkins_today : 1;

  return (
    <section aria-label="Key Performance Indicators" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-gutter">
      {/* KPI Card 1: Active Patients */}
      <div className="bg-surface-container-lowest p-space-md rounded-xl border border-outline-variant/30 flex flex-col justify-between transition-colors hover:border-primary/40 shadow-xs">
        <div className="flex items-center justify-between mb-space-xs">
          <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">
            Active Patients
          </span>
          <span className="material-symbols-outlined text-[18px] text-primary">personal_injury</span>
        </div>
        <div className="flex items-baseline gap-space-xs my-1">
          <span className="font-metric-tabular text-metric-tabular text-on-surface font-bold tracking-tight">
            {activePatients}
          </span>
          <span className="font-label-sm text-label-sm text-primary font-medium">
            100% capacity
          </span>
        </div>
        <p className="font-body-sm text-body-sm text-on-surface-variant">
          Enrolled knee arthroplasty cohort
        </p>
      </div>

      {/* KPI Card 2: Open Alerts */}
      <div className="bg-surface-container-lowest p-space-md rounded-xl border border-outline-variant/30 flex flex-col justify-between transition-colors hover:border-primary/40 shadow-xs">
        <div className="flex items-center justify-between mb-space-xs">
          <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">
            Open Alerts
          </span>
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-error opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-error"></span>
          </span>
        </div>
        <div className="flex items-baseline gap-space-xs my-1">
          <span className="font-metric-tabular text-metric-tabular text-error font-bold tracking-tight">
            {openAlerts}
          </span>
          <span className="font-label-sm text-label-sm text-error font-medium">
            Escalated review items
          </span>
        </div>
        <p className="font-body-sm text-body-sm text-on-surface-variant">
          Immediate attention required
        </p>
      </div>

      {/* KPI Card 3: SLA Compliance */}
      <div className="bg-surface-container-lowest p-space-md rounded-xl border border-outline-variant/30 flex flex-col justify-between transition-colors hover:border-primary/40 shadow-xs">
        <div className="flex items-center justify-between mb-space-xs">
          <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">
            Ack &lt;15m Response
          </span>
          <span className="material-symbols-outlined text-[18px] text-primary">timer</span>
        </div>
        <div className="flex items-baseline gap-space-xs my-1">
          <span className="font-metric-tabular text-metric-tabular text-primary font-bold tracking-tight">
            {ackRate}
          </span>
          <span className="font-label-sm text-label-sm text-primary font-medium">
            Rolling 7d compliance
          </span>
        </div>
        <p className="font-body-sm text-body-sm text-on-surface-variant">
          Target ≥90% SLA compliant
        </p>
      </div>

      {/* KPI Card 4: Missed Check-ins */}
      <div className="bg-surface-container-lowest p-space-md rounded-xl border border-outline-variant/30 flex flex-col justify-between transition-colors hover:border-primary/40 shadow-xs">
        <div className="flex items-center justify-between mb-space-xs">
          <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">
            Missed Check-ins Today
          </span>
          <span className="material-symbols-outlined text-[18px] text-tertiary">schedule</span>
        </div>
        <div className="flex items-baseline gap-space-xs my-1">
          <span className="font-metric-tabular text-metric-tabular text-tertiary font-bold tracking-tight">
            {missedCheckins}
          </span>
          <span className="font-label-sm text-label-sm text-tertiary font-medium">
            Overdue cadence
          </span>
        </div>
        <p className="font-body-sm text-body-sm text-on-surface-variant">
          WhatsApp check-in window elapsed
        </p>
      </div>
    </section>
  );
}
