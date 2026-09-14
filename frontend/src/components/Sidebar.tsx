"use client";

import React from "react";

interface NavItem {
  id: string;
  icon: string;
  label: string;
  active?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { id: "dashboard", icon: "grid_view", label: "Dashboard", active: true },
  { id: "patients", icon: "personal_injury", label: "Patients" },
  { id: "alerts", icon: "crisis_alert", label: "Alerts" },
  { id: "enrollment", icon: "how_to_reg", label: "Enrollment" },
  { id: "rulesets", icon: "rule_settings", label: "Rulesets" },
  { id: "hospitals", icon: "domain", label: "Hospitals" },
  { id: "whatsapp", icon: "chat", label: "WhatsApp Templates" },
  { id: "reports", icon: "analytics", label: "Reports" },
  { id: "settings", icon: "settings", label: "Settings" },
];

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-full w-[72px] bg-surface-container-lowest border-r border-outline-variant/30 z-50 flex flex-col justify-between items-center py-space-md">
      <div className="flex flex-col items-center w-full">
        {/* Brand Icon */}
        <div className="group relative flex items-center justify-center mb-space-lg">
          <div className="w-10 h-10 rounded-xl bg-primary-container/20 flex items-center justify-center text-primary font-bold text-lg border border-primary/30">
            <span className="material-symbols-outlined text-[24px] text-primary">healing</span>
          </div>
          <div className="absolute left-full ml-space-sm px-space-sm py-space-xs bg-inverse-surface text-inverse-on-surface font-label-sm text-label-sm rounded shadow-sm opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity whitespace-nowrap z-50">
            ERAS Remote Monitoring
          </div>
        </div>

        {/* Navigation Items */}
        <nav className="flex flex-col items-center gap-space-xs w-full">
          {NAV_ITEMS.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              className={`group relative flex items-center justify-center w-11 h-11 rounded-lg transition-colors ${
                item.active
                  ? "bg-surface-container-low text-primary relative before:content-[''] before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:h-7 before:w-[3px] before:bg-primary before:rounded-r font-semibold"
                  : "text-on-surface-variant hover:bg-surface-container-low hover:text-primary"
              }`}
            >
              <span className="material-symbols-outlined text-[22px]">{item.icon}</span>
              <div className="absolute left-full ml-space-sm px-space-sm py-space-xs bg-inverse-surface text-inverse-on-surface font-label-sm text-label-sm rounded opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity whitespace-nowrap z-50">
                {item.label}
              </div>
            </a>
          ))}
        </nav>
      </div>

      {/* Profile Avatar */}
      <div className="group relative flex flex-col items-center cursor-pointer">
        <div className="relative">
          <div className="w-9 h-9 rounded-full bg-primary/20 border border-primary/40 flex items-center justify-center text-primary font-semibold text-xs">
            SJ
          </div>
          <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-surface-container-lowest"></span>
        </div>
        <div className="absolute left-full ml-space-sm px-space-sm py-space-xs bg-inverse-surface text-inverse-on-surface font-label-sm text-label-sm rounded opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity whitespace-nowrap z-50">
          Nurse Admin Sarah J. (Online)
        </div>
      </div>
    </aside>
  );
}
