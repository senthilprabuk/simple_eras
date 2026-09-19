import React from "react";
import type { KpiResponse } from "@/lib/api";
import { formatDuration, quietCohort } from "@/lib/triage";

interface KpiMetricsProps {
  kpis: KpiResponse | null;
}

function Card({
  label,
  icon,
  value,
  detail,
  tone = "text-on-surface",
}: {
  label: string;
  icon: string;
  value: string;
  detail: string;
  tone?: string;
}) {
  return (
    <div className="bg-surface-container-lowest p-space-md rounded-xl border border-outline-variant/30 flex flex-col justify-between shadow-xs">
      <div className="flex items-center justify-between mb-space-xs">
        <span className="font-label-sm text-on-surface-variant uppercase tracking-wider">{label}</span>
        <span className="material-symbols-outlined text-[18px] text-primary" aria-hidden="true">{icon}</span>
      </div>
      <span className={`font-metric-tabular font-bold tracking-tight my-1 ${tone}`}>{value}</span>
      <p className="font-body-sm text-on-surface-variant">{detail}</p>
    </div>
  );
}

export default function KpiMetrics({ kpis }: KpiMetricsProps) {
  if (!kpis) {
    return (
      <section aria-label="Key figures" aria-busy="true" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-gutter">
        {["Active patients", "Unresolved alerts", "Acknowledged in time", "Missed check-ins today"].map((label) => (
          <Card key={label} label={label} icon="hourglass_empty" value="—" detail="Loading…" />
        ))}
      </section>
    );
  }

  const ackWindow = formatDuration(kpis.ack_window_secs);
  const compliance = kpis.ack_compliance_pct;

  return (
    <section aria-label="Key figures" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-gutter">
      <Card
        label="Active patients"
        icon="personal_injury"
        value={String(kpis.active_patients)}
        detail={`${quietCohort(kpis)} with no open alerts · ${kpis.patients_with_open_alerts} with alerts`}
      />
      <Card
        label="Unresolved alerts"
        icon="notification_important"
        value={String(kpis.unresolved_alerts)}
        tone={kpis.unacknowledged_alerts > 0 ? "text-error" : "text-on-surface"}
        detail={`${kpis.unacknowledged_alerts} not yet acknowledged`}
      />
      <Card
        label={`Acknowledged within ${ackWindow}`}
        icon="timer"
        value={compliance === null ? "—" : `${compliance.toFixed(1)}%`}
        tone={compliance !== null && compliance < 90 ? "text-error" : "text-primary"}
        detail={
          kpis.ack_decided_alerts === 0
            ? `No alerts came due in the last ${kpis.window_days} days`
            : `Of ${kpis.ack_decided_alerts} alerts due in the last ${kpis.window_days} days`
        }
      />
      <Card
        label="Missed check-ins today"
        icon="schedule"
        value={String(kpis.missed_checkins_today)}
        tone={kpis.missed_checkins_today > 0 ? "text-tertiary" : "text-on-surface"}
        detail="Today in the hospital's own timezone"
      />
    </section>
  );
}
