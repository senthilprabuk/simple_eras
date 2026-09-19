"use client";

import React from "react";
import Link from "next/link";
import { initials } from "@/lib/triage";

interface SidebarProps {
  fullName: string;
  role: string;
  onSignOut: () => void;
}

// Only the dashboard exists so far; the rest are placeholders for pages 2-9.
const PLANNED_PAGES = [
  { icon: "personal_injury", label: "Patients" },
  { icon: "how_to_reg", label: "Enrollment" },
  { icon: "rule_settings", label: "Rulesets" },
  { icon: "domain", label: "Hospitals" },
  { icon: "chat", label: "WhatsApp templates" },
  { icon: "analytics", label: "Reports" },
  { icon: "settings", label: "Settings" },
];

function Tooltip({ children }: { children: React.ReactNode }) {
  return (
    <span className="absolute left-full ml-space-sm px-space-sm py-space-xs bg-inverse-surface text-inverse-on-surface font-label-sm rounded opacity-0 pointer-events-none group-hover:opacity-100 group-focus-visible:opacity-100 transition-opacity whitespace-nowrap z-50">
      {children}
    </span>
  );
}

export default function Sidebar({ fullName, role, onSignOut }: SidebarProps) {
  return (
    <aside className="fixed left-0 top-0 h-full w-[72px] bg-surface-container-lowest border-r border-outline-variant/30 z-50 flex flex-col justify-between items-center py-space-md">
      <div className="flex flex-col items-center w-full">
        <div className="w-10 h-10 mb-space-lg rounded-xl bg-primary-container/20 flex items-center justify-center border border-primary/30">
          <span className="material-symbols-outlined text-[24px] text-primary" aria-label="ERAS Remote Monitoring">
            healing
          </span>
        </div>

        <nav aria-label="Main" className="flex flex-col items-center gap-space-xs w-full">
          <Link
            href="/"
            aria-current="page"
            className="group relative flex items-center justify-center w-11 h-11 rounded-lg bg-surface-container-low text-primary"
          >
            <span className="material-symbols-outlined text-[22px]" aria-hidden="true">grid_view</span>
            <span className="sr-only">Dashboard</span>
            <Tooltip>Dashboard</Tooltip>
          </Link>
          {PLANNED_PAGES.map((page) => (
            <span
              key={page.label}
              aria-disabled="true"
              className="group relative flex items-center justify-center w-11 h-11 rounded-lg text-outline-variant cursor-not-allowed"
            >
              <span className="material-symbols-outlined text-[22px]" aria-hidden="true">{page.icon}</span>
              <span className="sr-only">{page.label} (not available yet)</span>
              <Tooltip>{page.label} — not built yet</Tooltip>
            </span>
          ))}
        </nav>
      </div>

      <div className="flex flex-col items-center gap-space-sm">
        <div
          className="group relative w-9 h-9 rounded-full bg-primary/20 border border-primary/40 flex items-center justify-center text-primary font-semibold text-xs"
          title={`${fullName} (${role})`}
        >
          {initials(fullName)}
          <Tooltip>
            {fullName} · {role}
          </Tooltip>
        </div>
        <button
          type="button"
          onClick={onSignOut}
          className="group relative flex items-center justify-center w-9 h-9 rounded-lg text-on-surface-variant hover:bg-surface-container-low hover:text-error cursor-pointer"
        >
          <span className="material-symbols-outlined text-[20px]" aria-hidden="true">logout</span>
          <span className="sr-only">Sign out</span>
          <Tooltip>Sign out</Tooltip>
        </button>
      </div>
    </aside>
  );
}
