"use client";

import React, { useState } from "react";

interface TopHeaderProps {
  searchQuery?: string;
  onSearchChange?: (query: string) => void;
}

export default function TopHeader({ searchQuery = "", onSearchChange }: TopHeaderProps) {
  const [protocolTriggered, setProtocolTriggered] = useState(false);

  return (
    <header className="fixed top-0 left-[72px] right-0 h-14 bg-surface-container-lowest border-b border-outline-variant/30 z-40 px-gutter flex items-center justify-between">
      {/* Title & Cohort */}
      <div className="flex items-center gap-space-sm">
        <span className="font-headline-md text-headline-md text-on-surface font-semibold tracking-tight">
          Risk Queue
        </span>
        <span className="h-4 w-px bg-outline-variant/40 mx-space-xs"></span>
        <span className="font-body-sm text-body-sm text-on-surface-variant">
          Post-Op Knee Replacement Remote Cohort
        </span>
      </div>

      {/* Controls & Status */}
      <div className="flex items-center gap-space-md">
        {/* Search */}
        <div className="relative hidden lg:flex items-center">
          <span className="material-symbols-outlined absolute left-2.5 text-outline text-[18px]">
            search
          </span>
          <input
            className="w-64 pl-8 pr-12 py-1.5 bg-surface-container-lowest border border-outline-variant/40 rounded font-body-sm text-body-sm text-on-surface placeholder:text-outline focus:outline-none focus:border-primary"
            placeholder="Search patient name or MRN..."
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange?.(e.target.value)}
          />
          <kbd className="absolute right-2 px-1.5 py-0.5 border border-outline-variant/40 rounded font-label-sm text-[10px] text-outline bg-surface-bright">
            ⌘K
          </kbd>
        </div>

        {/* Clinic Selector */}
        <div className="flex items-center gap-1.5 px-space-sm py-1 border border-outline-variant/40 rounded bg-surface-container-lowest font-body-sm text-body-sm text-on-surface cursor-pointer hover:border-primary transition-colors">
          <span className="material-symbols-outlined text-[18px] text-primary">domain</span>
          <span className="font-label-md text-label-md">St. Mary's Orthopedic Center — Wing B</span>
          <span className="material-symbols-outlined text-[16px] text-outline">expand_more</span>
        </div>

        {/* Sync status */}
        <div className="flex items-center gap-space-xs font-body-sm text-body-sm text-on-surface-variant pl-space-xs">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
          </span>
          <span>Last synced 12s ago</span>
        </div>

        {/* Notification bell */}
        <button
          aria-label="Notifications"
          className="relative p-1.5 text-on-surface-variant hover:text-on-surface rounded hover:bg-surface-container-high transition-colors"
        >
          <span className="material-symbols-outlined text-[20px]">notifications</span>
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-error ring-1 ring-surface-container-lowest"></span>
        </button>

        {/* Emergency Call Protocol Button */}
        <button
          onClick={() => setProtocolTriggered((prev) => !prev)}
          className={`flex items-center gap-1.5 px-space-sm py-1 rounded font-label-md text-label-md transition-opacity ${
            protocolTriggered
              ? "bg-error text-white ring-2 ring-error"
              : "bg-error-container text-on-error-container hover:opacity-90"
          }`}
        >
          <span className="material-symbols-outlined text-[16px]">e911_emergency</span>
          <span>{protocolTriggered ? "Protocol Active" : "Call Protocol"}</span>
        </button>
      </div>
    </header>
  );
}
