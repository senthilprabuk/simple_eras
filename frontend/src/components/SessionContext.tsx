"use client";

import { createContext, useContext } from "react";
import type { Session } from "@/lib/session";

export const SessionContext = createContext<Session | null>(null);

/** The signed-in clinician. Only valid inside the (clinical) layout, which renders nothing until there is one. */
export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside the clinical layout");
  return session;
}
