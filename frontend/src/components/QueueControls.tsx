"use client";

import React from "react";

interface QueueControlsProps {
  currentPod: string;
  onSelectPod: (pod: string) => void;
  counts: {
    emergency: number;
    critical: number;
    review: number;
    missed: number;
  };
}

export default function QueueControls({
  currentPod,
  onSelectPod,
  counts,
}: QueueControlsProps) {
  return (
    <section className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
      <div className="flex flex-wrap items-center gap-space-sm">
        <h2 className="font-headline-md text-headline-md text-on-surface font-semibold tracking-tight">
          Prioritized Clinical Queue
        </h2>
        {/* Immutable Locked Order Indicator */}
        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-surface-container-low text-primary border border-outline-variant/30 font-label-sm text-label-sm">
          <span className="material-symbols-outlined text-[14px]">lock</span>
          <span>Server-Triage Locked (Severity → Alert Age)</span>
        </div>
      </div>

      {/* Cohort Severity Distribution Status Badges & Pod Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center bg-surface-container-lowest border border-outline-variant/30 rounded px-2.5 py-1 text-on-surface-variant font-label-sm text-label-sm">
          <span className="text-error font-semibold mr-1.5">{counts.emergency}</span> Emergency
          <span className="mx-2 text-outline-variant">·</span>
          <span className="text-error font-semibold mr-1.5">{counts.critical}</span> Critical
          <span className="mx-2 text-outline-variant">·</span>
          <span className="text-tertiary font-semibold mr-1.5">{counts.review}</span> Review
          <span className="mx-2 text-outline-variant">·</span>
          <span className="text-on-surface-variant font-semibold mr-1.5">{counts.missed}</span> Missed
        </div>

        <div className="inline-flex items-center rounded border border-outline-variant/30 bg-surface-container-lowest p-0.5">
          <button
            type="button"
            onClick={() => onSelectPod("all")}
            className={`px-3 py-1 rounded font-label-sm text-label-sm transition-colors ${
              currentPod === "all"
                ? "bg-surface-container-low text-primary font-semibold"
                : "text-on-surface-variant hover:text-on-surface"
            }`}
          >
            All Tiers ({counts.emergency + counts.critical + counts.review + counts.missed})
          </button>
          <button
            type="button"
            onClick={() => onSelectPod("poda")}
            className={`px-3 py-1 rounded font-label-sm text-label-sm transition-colors ${
              currentPod === "poda"
                ? "bg-surface-container-low text-primary font-semibold"
                : "text-on-surface-variant hover:text-on-surface"
            }`}
          >
            Pod A (East)
          </button>
          <button
            type="button"
            onClick={() => onSelectPod("podb")}
            className={`px-3 py-1 rounded font-label-sm text-label-sm transition-colors ${
              currentPod === "podb"
                ? "bg-surface-container-low text-primary font-semibold"
                : "text-on-surface-variant hover:text-on-surface"
            }`}
          >
            Pod B (West)
          </button>
        </div>
      </div>
    </section>
  );
}
