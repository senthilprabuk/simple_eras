/**
 * The signed-in clinician, held in sessionStorage so it ends when the tab
 * closes — the expected behaviour on a shared ward workstation.
 */

export interface Session {
  token: string;
  expiresAt: number;
  adminUserId: string;
  /** Null for an app admin, who belongs to no hospital. */
  hospitalId: number | null;
  hospitalName: string | null;
  fullName: string;
  role: string;
}

/** A clinician's session: always tied to one hospital. */
export interface ClinicalSession extends Session {
  hospitalId: number;
  hospitalName: string;
}

/** Manages hospitals and rulesets for the whole platform, at /app_admin; never sees a patient. */
export const APP_ADMIN_ROLE = "app_admin";

export function isClinicalSession(session: Session): session is ClinicalSession {
  return session.role !== APP_ADMIN_ROLE && session.hospitalId !== null && session.hospitalName !== null;
}

/** Where a signed-in user belongs: app admins in the admin area, clinicians on the dashboard. */
export function homePath(session: Session): string {
  return session.role === APP_ADMIN_ROLE ? "/app_admin" : "/";
}

/** Whether a path is one this user may open, so a sign-in link cannot land them in the wrong area. */
export function allowedPath(session: Session, path: string): boolean {
  const inAdminArea = path === "/app_admin" || path.startsWith("/app_admin/");
  return session.role === APP_ADMIN_ROLE ? inAdminArea : !inAdminArea;
}

const KEY = "eras.session";
const listeners = new Set<() => void>();

let cachedRaw: string | null | undefined;
let cachedSession: Session | null = null;

function parse(raw: string | null): Session | null {
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as Session;
    return session.expiresAt > Date.now() ? session : null;
  } catch {
    return null;
  }
}

export function loadSession(): Session | null {
  if (typeof window === "undefined") return null;
  return parse(window.sessionStorage.getItem(KEY));
}

/** Snapshot for useSyncExternalStore: stable identity until storage changes. */
export function getSessionSnapshot(): Session | null {
  const raw = window.sessionStorage.getItem(KEY);
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedSession = parse(raw);
  }
  return cachedSession;
}

export function subscribeSession(onChange: () => void): () => void {
  listeners.add(onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function saveSession(session: Session): void {
  window.sessionStorage.setItem(KEY, JSON.stringify(session));
  listeners.forEach((notify) => notify());
}

export function clearSession(): void {
  window.sessionStorage.removeItem(KEY);
  listeners.forEach((notify) => notify());
}

/** Full page load, not client routing, so no patient data survives in memory after sign-out. */
export function signOut(): void {
  clearSession();
  window.location.replace("/login");
}
