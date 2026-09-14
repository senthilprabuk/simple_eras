import React from "react";

export default function TriageStatusBanner() {
  return (
    <section className="bg-surface-container-lowest border border-outline-variant/30 rounded-xl p-space-md flex flex-col md:flex-row items-center justify-between gap-space-md shadow-sm">
      <div className="flex items-start md:items-center gap-space-sm">
        <div className="p-2 rounded bg-surface-container-low text-primary shrink-0">
          <span className="material-symbols-outlined text-[22px]">health_and_safety</span>
        </div>
        <div>
          <h3 className="font-title-sm text-title-sm font-semibold text-on-surface">
            Automated ERAS Triage Routine
          </h3>
          <p className="font-body-sm text-body-sm text-on-surface-variant">
            Automated triage running every 60 seconds across 142 enrolled knee replacement patients. Normal tier patients (135) progressing without alerts — next scheduled check-in cycle at 14:00.
          </p>
        </div>
      </div>
      <div className="flex items-center gap-space-xs shrink-0 self-end md:self-auto">
        <button
          type="button"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-bright border border-outline-variant/40 text-on-surface-variant hover:text-on-surface hover:border-outline-variant font-label-md text-label-md transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined text-[16px] text-primary">
            check_circle_outline
          </span>
          <span>View Quiet Cohort (135 Normal)</span>
        </button>
        <button
          type="button"
          aria-label="Triage Engine Settings"
          className="p-1.5 rounded border border-outline-variant/30 text-on-surface-variant hover:text-primary hover:bg-surface-container-low transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined text-[18px]">tune</span>
        </button>
      </div>
    </section>
  );
}
