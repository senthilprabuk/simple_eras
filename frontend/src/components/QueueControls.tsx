"use client";

import React from "react";

interface QueueControlsProps {
  currentPod: string;
  onSelectPod: (pod: string) => void;
  currentTier?: string;
  onSelectTier?: (tier: string) => void;
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
  currentTier = "all",
  onSelectTier,
  counts,
}: QueueControlsProps) {
  const totalAlerts = counts.emergency + counts.critical + counts.review + counts.missed;

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

      {/* Cohort Severity Distribution Interactive Badges & Pod Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center bg-surface-container-lowest border border-outline-variant/30 rounded p-0.5 text-on-surface-variant font-label-sm text-label-sm">
          <button
            type="button"
            onClick={() => onSelectTier?.("all")}
            className={`px-2 py-0.5 rounded cursor-pointer transition-colors ${
              currentTier === "all" ? "bg-surface-container-low font-semibold text-primary" : "hover:text-on-surface"
            }`}
          >
            All ({totalAlerts})
          </button>
          <span className="mx-1 text-outline-variant/60">·</span>
          <button
            type="button"
            onClick={() => onSelectTier?.(currentTier === "emergency" ? "all" : "emergency")}
            className={`px-2 py-0.5 rounded cursor-pointer transition-colors ${
              currentTier === "emergency" ? "bg-error text-white font-semibold" : "hover:text-error"
            }`}
          >
            <span className={currentTier === "emergency" ? "text-white" : "text-error font-semibold"}>
              {counts.emergency}
            </span>{" "}
            Emergency
          </button>
          <span className="mx-1 text-outline-variant/60">·</span>
          <button
            type="button"
            onClick={() => onSelectTier?.(currentTier === "critical" ? "all" : "critical")}
            className={`px-2 py-0.5 rounded cursor-pointer transition-colors ${
              currentTier === "critical" ? "bg-error/15 border border-error text-error font-semibold" : "hover:text-error"
            }`}
          >
            <span className="text-error font-semibold">{counts.critical}</span> Critical
          </button>
          <span className="mx-1 text-outline-variant/60">·</span>
          <button
            type="button"
            onClick={() => onSelectTier?.(currentTier === "review" ? "all" : "review")}
            className={`px-2 py-0.5 rounded cursor-pointer transition-colors ${
              currentTier === "review" ? "bg-tertiary-fixed text-on-tertiary-fixed font-semibold" : "hover:text-tertiary"
            }`}
          >
            <span className="text-tertiary font-semibold">{counts.review}</span> Review
          </button>
          <span className="mx-1 text-outline-variant/60">·</span>
          <button
            type="button"
            onClick={() => onSelectTier?.(currentTier === "missed" ? "all" : "missed")}
            className={`px-2 py-0.5 rounded cursor-pointer transition-colors ${
              currentTier === "missed" ? "bg-surface-bright border border-outline-variant text-on-surface font-semibold" : "hover:text-on-surface"
            }`}
          >
            <span className="text-on-surface-variant font-semibold">{counts.missed}</span> Missed
          </button>
        </div>

        <div className="inline-flex items-center rounded border border-outline-variant/30 bg-surface-container-lowest p-0.5">
          <button
            type="button"
            onClick={() => onSelectPod("all")}
            className={`px-3 py-1 rounded font-label-sm text-label-sm cursor-pointer transition-colors ${
              currentPod === "all"
                ? "bg-surface-container-low text-primary font-semibold"
                : "text-on-surface-variant hover:text-on-surface"
            }`}
          >
            All Pods
          </button>
          <button
            type="button"
            onClick={() => onSelectPod("poda")}
            className={`px-3 py-1 rounded font-label-sm text-label-sm cursor-pointer transition-colors ${
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
            className={`px-3 py-1 rounded font-label-sm text-label-sm cursor-pointer transition-colors ${
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
