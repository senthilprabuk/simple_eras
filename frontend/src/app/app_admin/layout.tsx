"use client";

import React, { useEffect, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import Sidebar, { type NavItem } from "@/components/Sidebar";
import { HeaderBar } from "@/components/ui";
import { redirectToLogin } from "@/lib/api";
import { APP_ADMIN_ROLE, getSessionSnapshot, homePath, loadSession, signOut, subscribeSession } from "@/lib/session";

const ADMIN_NAV: NavItem[] = [
  { href: "/app_admin/hospitals", icon: "domain_add", label: "Hospitals" },
  { href: "/app_admin/rulesets", icon: "rule_settings", label: "Rulesets" },
];

/** The platform admin area. Only app admins get in; clinicians are sent back to their dashboard. */
export default function AppAdminLayout({ children }: { children: React.ReactNode }) {
  const session = useSyncExternalStore(subscribeSession, getSessionSnapshot, () => null);
  const pathname = usePathname();

  useEffect(() => {
    const current = loadSession();
    if (!current) redirectToLogin();
    else if (current.role !== APP_ADMIN_ROLE) window.location.replace(homePath(current));
  }, []);

  if (!session || session.role !== APP_ADMIN_ROLE) {
    return (
      <div className="min-h-screen bg-surface-bright flex items-center justify-center">
        <span className="font-body-md text-on-surface-variant">Loading…</span>
      </div>
    );
  }

  const title = ADMIN_NAV.find((item) => pathname.startsWith(item.href))?.label ?? "App admin";
  return (
    <div className="min-h-screen bg-surface-bright text-on-surface">
      <Sidebar fullName={session.fullName} role="App admin" onSignOut={signOut} nav={ADMIN_NAV} />
      <HeaderBar title={title} place="Platform administration" placeIcon="admin_panel_settings" fullName={session.fullName} />
      <div className="pl-[72px]">{children}</div>
    </div>
  );
}
