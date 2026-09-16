"use client";

import React, { useState } from "react";

interface TriageStatusBannerProps {
  onTriggerSweep?: () => Promise<void>;
  normalCount?: number;
  totalEnrolled?: number;
}

export default function TriageStatusBanner({
  onTriggerSweep,
  normalCount = 6,
  totalEnrolled = 13,
}: TriageStatusBannerProps) {
  const [isSweeping, setIsSweeping] = useState(false);
  const [quietCohortExpanded, setQuietCohortExpanded] = useState(false);

  const handleSweepClick = async () => {
    if (!onTriggerSweep) return;
    setIsSweeping(true);
    try {
      await onTriggerSweep();
    } finally {
      setTimeout(() => setIsSweeping(false), 600);
    }
  };

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
            Automated in-process sweep evaluating alerts every 60 seconds across {totalEnrolled} active knee replacement patients. Normal tier patients ({normalCount}) progressing without alerts — next scheduled cycle in progress.
          </p>
        </div>
      </div>
      <div className="flex items-center gap-space-xs shrink-0 self-end md:self-auto">
        <button
          type="button"
          disabled={isSweeping}
          onClick={handleSweepClick}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container-low border border-primary/40 text-primary hover:bg-surface-container-high font-label-md text-label-md transition-colors cursor-pointer disabled:opacity-50"
        >
          <span className={`material-symbols-outlined text-[16px] ${isSweeping ? "animate-spin" : ""}`}>
            {isSweeping ? "sync" : "bolt"}
          </span>
          <span>{isSweeping ? "Sweeping Alerts..." : "Trigger Sweep Now"}</span>
        </button>

        <button
          type="button"
          onClick={() => setQuietCohortExpanded(!quietCohortExpanded)}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded border font-label-md text-label-md transition-colors cursor-pointer ${
            quietCohortExpanded
              ? "bg-primary/10 border-primary text-primary font-semibold"
              : "bg-surface-bright border-outline-variant/40 text-on-surface-variant hover:text-on-surface hover:border-outline-variant"
          }`}
        >
          <span className="material-symbols-outlined text-[16px] text-primary">
            check_circle_outline
          </span>
          <span>Quiet Cohort ({normalCount} Normal)</span>
        </button>
      </div>
    </section>
  );
}
