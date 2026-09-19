"use client";

import React, { useEffect, useSyncExternalStore } from "react";
import Sidebar from "@/components/Sidebar";
import { SessionContext } from "@/components/SessionContext";
import { redirectToLogin } from "@/lib/api";
import { getSessionSnapshot, homePath, isClinicalSession, loadSession, signOut, subscribeSession } from "@/lib/session";

/**
 * Every clinician screen: nothing renders until there is a clinician's
 * session, so pages can assume one and never render patient data on the
 * server. An app admin is sent to the admin area instead.
 */
export default function ClinicalLayout({ children }: { children: React.ReactNode }) {
  const session = useSyncExternalStore(subscribeSession, getSessionSnapshot, () => null);

  useEffect(() => {
    const current = loadSession();
    if (!current) redirectToLogin();
    else if (!isClinicalSession(current)) window.location.replace(homePath(current));
  }, []);

  if (!session || !isClinicalSession(session)) {
    return (
      <div className="min-h-screen bg-surface-bright flex items-center justify-center">
        <span className="font-body-md text-on-surface-variant">Loading…</span>
      </div>
    );
  }

  return (
    <SessionContext.Provider value={session}>
      <div className="min-h-screen bg-surface-bright text-on-surface">
        <Sidebar fullName={session.fullName} role={session.role} onSignOut={signOut} />
        <div className="pl-[72px]">{children}</div>
      </div>
    </SessionContext.Provider>
  );
}
