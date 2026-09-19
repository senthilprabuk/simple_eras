"use client";

import React from "react";
import { formatDuration } from "@/lib/triage";

interface TopHeaderProps {
  hospitalName: string;
  fullName: string;
  lastRefreshed: number | null;
  now: number;
  refreshing: boolean;
  onRefresh: () => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
}

export default function TopHeader({
  hospitalName,
  fullName,
  lastRefreshed,
  now,
  refreshing,
  onRefresh,
  searchQuery,
  onSearchChange,
}: TopHeaderProps) {
  const freshness = refreshing
    ? "Updating…"
    : lastRefreshed === null
      ? "Not updated yet"
      : `Updated ${formatDuration(Math.max(0, (now - lastRefreshed) / 1000))} ago`;

  return (
    <header className="fixed top-0 left-[72px] right-0 h-14 bg-surface-container-lowest border-b border-outline-variant/30 z-40 px-gutter flex items-center justify-between gap-space-md">
      <div className="flex items-center gap-space-sm min-w-0">
        <span className="font-headline-md text-on-surface tracking-tight">Risk Queue</span>
        <span className="h-4 w-px bg-outline-variant/40" aria-hidden="true" />
        <span className="flex items-center gap-1 font-label-md text-on-surface truncate">
          <span className="material-symbols-outlined text-[18px] text-primary" aria-hidden="true">domain</span>
          {hospitalName}
        </span>
      </div>

      <div className="flex items-center gap-space-md">
        <label className="relative hidden lg:flex items-center">
          <span className="sr-only">Search patient name or MRN</span>
          <span className="material-symbols-outlined absolute left-2.5 text-outline text-[18px]" aria-hidden="true">
            search
          </span>
          <input
            className="w-64 pl-8 pr-3 py-1.5 bg-surface-container-lowest border border-outline-variant/40 rounded font-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:border-primary"
            placeholder="Search patient name or MRN…"
            type="search"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </label>

        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="flex items-center gap-1 font-body-sm text-on-surface-variant hover:text-primary cursor-pointer disabled:cursor-default"
          aria-label="Refresh the queue now"
        >
          <span className={`material-symbols-outlined text-[18px] ${refreshing ? "animate-spin" : ""}`} aria-hidden="true">
            sync
          </span>
          <span aria-live="polite">{freshness}</span>
        </button>

        <span className="font-label-md text-on-surface hidden md:inline">{fullName}</span>
      </div>
    </header>
  );
}
