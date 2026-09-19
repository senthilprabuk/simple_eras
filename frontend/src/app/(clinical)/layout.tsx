"use client";

import React, { useEffect, useSyncExternalStore } from "react";
import Sidebar from "@/components/Sidebar";
import { SessionContext } from "@/components/SessionContext";
import { redirectToLogin } from "@/lib/api";
import { clearSession, getSessionSnapshot, loadSession, subscribeSession } from "@/lib/session";

/**
 * Every clinician screen: nothing renders until there is a session, so pages
 * can assume one and never render patient data on the server.
 */
export default function ClinicalLayout({ children }: { children: React.ReactNode }) {
  const session = useSyncExternalStore(subscribeSession, getSessionSnapshot, () => null);

  useEffect(() => {
    if (!loadSession()) redirectToLogin();
  }, []);

  if (!session) {
    return (
      <div className="min-h-screen bg-surface-bright flex items-center justify-center">
        <span className="font-body-md text-on-surface-variant">Loading…</span>
      </div>
    );
  }

  const signOut = () => {
    clearSession();
    // Full load so no patient data survives in memory after sign-out.
    window.location.replace("/login");
  };

  return (
    <SessionContext.Provider value={session}>
      <div className="min-h-screen bg-surface-bright text-on-surface">
        <Sidebar fullName={session.fullName} role={session.role} onSignOut={signOut} />
        <div className="pl-[72px]">{children}</div>
      </div>
    </SessionContext.Provider>
  );
}
