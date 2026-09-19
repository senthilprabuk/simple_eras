"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { initials } from "@/lib/triage";

export interface NavItem {
  href: string;
  icon: string;
  label: string;
}

interface SidebarProps {
  fullName: string;
  role: string;
  onSignOut: () => void;
  nav?: NavItem[];
}

const CLINICAL_NAV: NavItem[] = [
  { href: "/", icon: "grid_view", label: "Dashboard" },
  { href: "/patients", icon: "personal_injury", label: "Patients" },
  { href: "/alerts", icon: "crisis_alert", label: "Alerts" },
  { href: "/enrollment", icon: "how_to_reg", label: "Enrollment" },
  { href: "/rulesets", icon: "rule_settings", label: "Rulesets" },
  { href: "/hospitals", icon: "domain", label: "Hospitals" },
  { href: "/templates", icon: "chat", label: "WhatsApp templates" },
  { href: "/reports", icon: "analytics", label: "Reports" },
  { href: "/settings", icon: "settings", label: "Settings" },
];

function Tooltip({ children }: { children: React.ReactNode }) {
  return (
    <span className="absolute left-full ml-space-sm px-space-sm py-space-xs bg-inverse-surface text-inverse-on-surface font-label-sm rounded opacity-0 pointer-events-none group-hover:opacity-100 group-focus-visible:opacity-100 transition-opacity whitespace-nowrap z-50">
      {children}
    </span>
  );
}

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

export default function Sidebar({ fullName, role, onSignOut, nav = CLINICAL_NAV }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 h-full w-[72px] bg-surface-container-lowest border-r border-outline-variant/30 z-50 flex flex-col justify-between items-center py-space-md">
      <div className="flex flex-col items-center w-full">
        <div className="w-10 h-10 mb-space-lg rounded-xl bg-primary-container/20 flex items-center justify-center border border-primary/30">
          <span className="material-symbols-outlined text-[24px] text-primary" aria-label="ERAS Remote Monitoring">
            healing
          </span>
        </div>

        <nav aria-label="Main" className="flex flex-col items-center gap-space-xs w-full">
          {nav.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`group relative flex items-center justify-center w-11 h-11 rounded-lg transition-colors ${
                  active
                    ? "bg-surface-container-low text-primary before:content-[''] before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:h-7 before:w-[3px] before:bg-primary before:rounded-r"
                    : "text-on-surface-variant hover:bg-surface-container-low hover:text-primary"
                }`}
              >
                <span className="material-symbols-outlined text-[22px]" aria-hidden="true">{item.icon}</span>
                <span className="sr-only">{item.label}</span>
                <Tooltip>{item.label}</Tooltip>
              </Link>
            );
          })}
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
