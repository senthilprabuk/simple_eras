/**
 * The signed-in clinician, held in sessionStorage so it ends when the tab
 * closes — the expected behaviour on a shared ward workstation.
 */

export interface Session {
  token: string;
  expiresAt: number;
  adminUserId: string;
  hospitalId: number;
  hospitalName: string;
  fullName: string;
  role: string;
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
