"use client";

import { createContext, useContext } from "react";
import type { ClinicalSession } from "@/lib/session";

export const SessionContext = createContext<ClinicalSession | null>(null);

/** The signed-in clinician. Only valid inside the (clinical) layout, which renders nothing until there is one. */
export function useSession(): ClinicalSession {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside the clinical layout");
  return session;
}
