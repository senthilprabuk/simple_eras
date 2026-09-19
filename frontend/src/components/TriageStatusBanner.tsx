import React from "react";
import type { Health, KpiResponse } from "@/lib/api";
import { formatDuration, quietCohort } from "@/lib/triage";

interface TriageStatusBannerProps {
  kpis: KpiResponse | null;
  health: Health | null;
  hospitalName: string;
}

export default function TriageStatusBanner({ kpis, health, hospitalName }: TriageStatusBannerProps) {
  const ackWindow = kpis ? formatDuration(kpis.ack_window_secs) : "the hospital's window";

  return (
    <section className="flex flex-col gap-space-sm">
      {health?.notification_provider === "disabled" && (
        <div
          role="status"
          className="flex items-start gap-space-sm px-space-md py-space-sm rounded-xl bg-tertiary-fixed/60 border border-tertiary-fixed-dim text-on-tertiary-fixed"
        >
          <span className="material-symbols-outlined text-[20px] text-tertiary" aria-hidden="true">warning</span>
          <p className="font-body-md">
            Escalation notifications are not being delivered: no notification provider is configured on the
            server. Overdue alerts are marked escalated, but nobody is paged. Watch this queue directly.
          </p>
        </div>
      )}

      <div className="bg-surface-container-lowest border border-outline-variant/30 rounded-xl p-space-md flex items-start gap-space-sm shadow-sm">
        <span className="p-2 rounded bg-surface-container-low text-primary shrink-0">
          <span className="material-symbols-outlined text-[22px]" aria-hidden="true">health_and_safety</span>
        </span>
        <div>
          <h3 className="font-title-sm text-on-surface">Automated escalation</h3>
          <p className="font-body-sm text-on-surface-variant">
            Critical and emergency alerts not acknowledged within {ackWindow} are escalated to every active clinician
            at {hospitalName}. The server checks continuously; this page refreshes every 30 seconds.
            {kpis && ` ${quietCohort(kpis)} of ${kpis.active_patients} active patients currently have no open alerts.`}
          </p>
          {health && !health.scheduler_running && (
            <p role="alert" className="font-body-sm text-error mt-1">
              The escalation scheduler is not running on the server.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
