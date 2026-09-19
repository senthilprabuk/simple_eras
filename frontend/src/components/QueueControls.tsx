"use client";

import React from "react";
import type { Tier } from "@/lib/api";
import { TIERS } from "@/lib/triage";

interface QueueControlsProps {
  counts: Record<Tier, number>;
  total: number;
  loaded: number;
  tierFilter: Tier | "all";
  onTierFilter: (tier: Tier | "all") => void;
}

const TIER_LABEL: Record<Tier, string> = {
  emergency: "Emergency",
  critical: "Critical",
  review: "Review",
  missed: "Missed",
};

export default function QueueControls({ counts, total, loaded, tierFilter, onTierFilter }: QueueControlsProps) {
  const options: (Tier | "all")[] = ["all", ...TIERS];

  return (
    <section className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
      <div className="flex flex-wrap items-center gap-space-sm">
        <h2 className="font-headline-md text-on-surface tracking-tight">Prioritized clinical queue</h2>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-surface-container-low text-primary border border-outline-variant/30 font-label-sm">
          <span className="material-symbols-outlined text-[14px]" aria-hidden="true">sort</span>
          Ordered by severity, then oldest first
        </span>
        {total > loaded && (
          <span className="font-body-sm text-on-surface-variant">
            Showing the first {loaded} of {total}
          </span>
        )}
      </div>

      <div
        role="group"
        aria-label="Filter by tier"
        className="flex items-center bg-surface-container-lowest border border-outline-variant/30 rounded p-0.5 font-label-sm text-on-surface-variant"
      >
        {options.map((option) => {
          const active = tierFilter === option;
          const count = option === "all" ? loaded : counts[option];
          return (
            <button
              key={option}
              type="button"
              aria-pressed={active}
              onClick={() => onTierFilter(active && option !== "all" ? "all" : option)}
              className={`px-2.5 py-1 rounded cursor-pointer transition-colors ${
                active ? "bg-surface-container-low font-semibold text-primary" : "hover:text-on-surface"
              }`}
            >
              {option === "all" ? "All" : TIER_LABEL[option]} ({count})
            </button>
          );
        })}
      </div>
    </section>
  );
}
